package com.behemoth.jforex.state;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Durable local execution cache used to deduplicate lifecycle sync across reconnects.
 */
public final class ExecutionStateStore {
    private final Path statePath;
    private final ObjectMapper objectMapper;
    private final Map<String, OcoGroupState> groupsByGroupLabel = new LinkedHashMap<>();
    private final Map<String, String> orderLabelToGroupLabel = new LinkedHashMap<>();

    public ExecutionStateStore(Path statePath, ObjectMapper objectMapper) {
        this.statePath = Objects.requireNonNull(statePath, "statePath");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
        load();
    }

    public synchronized OcoGroupState findByOrderLabel(String label) {
        String groupLabel = orderLabelToGroupLabel.get(label);
        return groupLabel == null ? null : groupsByGroupLabel.get(groupLabel);
    }

    public synchronized OcoLegRef markSubmitAccepted(String label, String orderId, double amountMillions) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.orderId = orderId;
        ref.leg.amountMillions = amountMillions;
        ref.leg.status = ref.leg.cancelRequested ? "CANCEL_REQUESTED" : "SUBMIT_OK";
        persist();
        return ref;
    }

    public synchronized OcoLegRef markRejected(String label, String detail) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.status = "REJECTED";
        ref.leg.lastMessage = detail;
        ref.group.lastError = detail;
        persist();
        return ref;
    }

    public synchronized FillAction markFilled(String label, String orderId, double fillPrice, Instant fillTs) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.orderId = orderId;
        ref.leg.fillPrice = fillPrice;
        ref.leg.fillEpochMs = fillTs.toEpochMilli();
        ref.leg.status = "FILLED";
        String siblingLabelToCancel = null;
        OcoGroupState.OcoLegState sibling = ref.group.siblingOf(label);
        if (sibling != null && sibling.isActive() && !sibling.cancelRequested) {
            sibling.cancelRequested = true;
            sibling.status = "CANCEL_REQUESTED";
            siblingLabelToCancel = sibling.label;
        }
        if (sibling != null && sibling.wasFilled()) {
            ref.group.lifecycleViolation = true;
            ref.group.lastError = "double_fill_detected";
        }
        boolean shouldNotifyTradeOpen = !ref.leg.openNotified;
        persist();
        return new FillAction(ref.group, ref.leg, siblingLabelToCancel, shouldNotifyTradeOpen, ref.group.lifecycleViolation);
    }

    public synchronized CloseAction markClosed(String label, double closePrice, Instant closeTs, Double pnlPips) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.closePrice = closePrice;
        ref.leg.closeEpochMs = closeTs.toEpochMilli();
        ref.leg.pnlPips = pnlPips;
        String tradeStatus = ref.leg.wasFilled() ? "CLOSED" : "CANCELLED";
        ref.leg.status = tradeStatus;
        boolean shouldTouch = ref.leg.wasFilled() && !ref.leg.touchNotified;
        boolean shouldUpdate = !ref.leg.updateNotified;
        persist();
        return new CloseAction(ref.group, ref.leg, shouldTouch, shouldUpdate, tradeStatus);
    }

    public synchronized void markCancelRequested(String label) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.cancelRequested = true;
        if (!"FILLED".equals(ref.leg.status)) {
            ref.leg.status = "CANCEL_REQUESTED";
        }
        persist();
    }

    public synchronized void markTradeOpenSynced(String label) {
        OcoLegRef ref = requireLeg(label);
        ref.leg.openNotified = true;
        persist();
    }

    public synchronized boolean markTradeTouchSynced(String label) {
        OcoLegRef ref = requireLeg(label);
        boolean changed = !ref.leg.touchNotified;
        ref.leg.touchNotified = true;
        persist();
        return changed;
    }

    public synchronized boolean markTradeUpdateSynced(String label) {
        OcoLegRef ref = requireLeg(label);
        boolean changed = !ref.leg.updateNotified;
        ref.leg.updateNotified = true;
        persist();
        return changed;
    }

    public synchronized Collection<OcoGroupState> groups() {
        return List.copyOf(groupsByGroupLabel.values());
    }

    public synchronized void persist() {
        try {
            Files.createDirectories(statePath.getParent());
            objectMapper.writerWithDefaultPrettyPrinter()
                    .writeValue(statePath.toFile(), new ArrayList<>(groupsByGroupLabel.values()));
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to persist JForex execution state", exc);
        }
    }

    private void load() {
        if (!Files.exists(statePath)) {
            return;
        }
        try {
            List<OcoGroupState> groups = objectMapper.readValue(statePath.toFile(), new TypeReference<>() {
            });
            groupsByGroupLabel.clear();
            orderLabelToGroupLabel.clear();
            for (OcoGroupState group : groups) {
                groupsByGroupLabel.put(group.groupLabel, group);
                index(group);
            }
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to load JForex execution state", exc);
        }
    }

    private OcoLegRef requireLeg(String label) {
        OcoGroupState group = findByOrderLabel(label);
        if (group == null) {
            throw new IllegalArgumentException("Unknown order label: " + label);
        }
        OcoGroupState.OcoLegState leg = group.legForLabel(label);
        if (leg == null) {
            throw new IllegalArgumentException("Unknown order label: " + label);
        }
        return new OcoLegRef(group, leg);
    }

    private void index(OcoGroupState group) {
        if (group.buyLeg != null && group.buyLeg.label != null) {
            orderLabelToGroupLabel.put(group.buyLeg.label, group.groupLabel);
        }
        if (group.sellLeg != null && group.sellLeg.label != null) {
            orderLabelToGroupLabel.put(group.sellLeg.label, group.groupLabel);
        }
    }

    public record OcoLegRef(OcoGroupState group, OcoGroupState.OcoLegState leg) {
    }

    public record FillAction(
            OcoGroupState group,
            OcoGroupState.OcoLegState leg,
            String siblingLabelToCancel,
            boolean shouldNotifyTradeOpen,
            boolean lifecycleViolation
    ) {
    }

    public record CloseAction(
            OcoGroupState group,
            OcoGroupState.OcoLegState leg,
            boolean shouldNotifyTouch,
            boolean shouldNotifyTradeUpdate,
            String tradeStatus
    ) {
    }
}
