package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.OrderEvent;
import com.behemoth.jforex.core.OrderEventType;
import com.behemoth.jforex.core.RuntimeInstrument;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.live.LiveReadinessCoordinator;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.state.ExecutionStateStore;
import com.dukascopy.api.IAccount;
import com.dukascopy.api.IBar;
import com.dukascopy.api.IContext;
import com.dukascopy.api.IMessage;
import com.dukascopy.api.IOrder;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.Period;
import java.net.http.HttpClient;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Thin JForex runtime shim that forwards Dukascopy callbacks into the shared strategy core.
 */
public final class BehemothJForexStrategy implements IStrategy {
    private final JForexSessionConfig sessionConfig;
    private final PythonPredictionClient predictionClient;
    private final JForexMetrics metrics;
    private final ExecutionStateStore stateStore;
    private final Stage14ArtifactWriter artifactWriter;
    private final Map<String, Instrument> instrumentsBySymbol = new LinkedHashMap<>();
    private BehemothStrategyCore core;
    private LiveReadinessCoordinator liveReadinessCoordinator;
    private IContext context;

    public BehemothJForexStrategy(JForexSessionConfig sessionConfig) {
        this(
                sessionConfig,
                new PythonPredictionClient(
                        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build(),
                        sessionConfig.apiBaseUri(),
                        Duration.ofSeconds(sessionConfig.apiTimeoutSeconds())
                ),
                JForexMetrics.start(sessionConfig)
        );
    }

    public BehemothJForexStrategy(JForexSessionConfig sessionConfig, JForexMetrics metrics) {
        this(
                sessionConfig,
                new PythonPredictionClient(
                        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build(),
                        sessionConfig.apiBaseUri(),
                        Duration.ofSeconds(sessionConfig.apiTimeoutSeconds())
                ),
                metrics
        );
    }

    BehemothJForexStrategy(
            JForexSessionConfig sessionConfig,
            PythonPredictionClient predictionClient,
            JForexMetrics metrics
    ) {
        this.sessionConfig = Objects.requireNonNull(sessionConfig, "sessionConfig");
        this.predictionClient = Objects.requireNonNull(predictionClient, "predictionClient");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        Path statePath = sessionConfig.reportDir().resolve("runtime").resolve("active_oco_state.json");
        this.stateStore = new ExecutionStateStore(statePath, predictionClient.objectMapper());
        this.artifactWriter = new Stage14ArtifactWriter(sessionConfig.reportDir(), "jforex");
    }

    @Override
    public void onStart(IContext context) throws JFException {
        try {
            this.context = Objects.requireNonNull(context, "context");
            List<RuntimeInstrument> runtimeInstruments = new ArrayList<>();
            for (String rawSymbol : sessionConfig.instruments()) {
                String symbol = normalizeSymbol(rawSymbol);
                Instrument instrument = Instrument.valueOf(symbol);
                instrumentsBySymbol.put(symbol, instrument);
                runtimeInstruments.add(new RuntimeInstrument(symbol, instrument.getPipValue()));
            }
            context.setSubscribedInstruments(Set.copyOf(instrumentsBySymbol.values()), true);
            this.core = new BehemothStrategyCore(
                    sessionConfig,
                    predictionClient,
                    stateStore,
                    artifactWriter,
                    metrics,
                    new JForexExecutionPort(() -> this.context == null ? null : this.context.getEngine(), instrumentsBySymbol)
            );
            core.start(runtimeInstruments);
            this.liveReadinessCoordinator = new LiveReadinessCoordinator(sessionConfig, predictionClient, metrics);
            liveReadinessCoordinator.initialize(context, core, runtimeInstruments.stream().map(RuntimeInstrument::symbol).toList());
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onTick(Instrument instrument, ITick tick) throws JFException {
        if (instrument == null || tick == null || core == null) {
            return;
        }
        try {
            Instant tickTs = Instant.ofEpochMilli(tick.getTime());
            String symbol = normalizeSymbol(instrument.name());
            if (liveReadinessCoordinator != null) {
                liveReadinessCoordinator.recordLiveTick(symbol, tickTs);
                liveReadinessCoordinator.onHeartbeat(tickTs);
            }
            core.onTick(new RuntimeTick(
                    symbol,
                    tickTs,
                    tick.getBid(),
                    tick.getAsk()
            ));
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) throws JFException {
        if (instrument == null || core == null) {
            return;
        }
        try {
            core.flushSymbol(normalizeSymbol(instrument.name()));
            if (liveReadinessCoordinator != null) {
                Instant heartbeatTs = bidBar != null
                        ? Instant.ofEpochMilli(bidBar.getTime())
                        : askBar != null
                        ? Instant.ofEpochMilli(askBar.getTime())
                        : Instant.now();
                liveReadinessCoordinator.onHeartbeat(heartbeatTs);
            }
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onMessage(IMessage message) throws JFException {
        try {
            OrderEvent event = toOrderEvent(message, message.getOrder());
            if (event != null) {
                core.onOrderEvent(event);
            }
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onAccount(IAccount account) throws JFException {
        if (account == null || core == null) {
            return;
        }
        try {
            core.onAccountSnapshot(account.getBalance(), account.getEquity(), Instant.now());
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onStop() throws JFException {
        try {
            if (liveReadinessCoordinator != null) {
                liveReadinessCoordinator.close();
                liveReadinessCoordinator = null;
            }
            if (core != null) {
                core.stop();
            }
        } catch (RuntimeException exc) {
            throw new JFException(exc.getMessage());
        } finally {
            metrics.close();
            context = null;
        }
    }

    private static OrderEvent toOrderEvent(IMessage message, IOrder order) throws JFException {
        OrderEventType type = switch (message.getType()) {
            case ORDER_SUBMIT_OK -> OrderEventType.SUBMIT_OK;
            case ORDER_SUBMIT_REJECTED -> OrderEventType.SUBMIT_REJECTED;
            case ORDER_FILL_OK -> OrderEventType.FILL_OK;
            case ORDER_FILL_REJECTED -> OrderEventType.FILL_REJECTED;
            case ORDER_CHANGED_REJECTED -> OrderEventType.CHANGE_REJECTED;
            case ORDER_CHANGED_OK -> OrderEventType.CHANGE_OK;
            case ORDER_CLOSE_OK -> OrderEventType.CLOSE_OK;
            case ORDER_CLOSE_REJECTED -> OrderEventType.CLOSE_REJECTED;
            default -> null;
        };
        if (type == null) {
            return null;
        }
        return new OrderEvent(
                type,
                normalizeSymbol(order.getInstrument().name()),
                order.getLabel(),
                order.getId(),
                order.getOpenPrice(),
                order.getFillTime() > 0L ? Instant.ofEpochMilli(order.getFillTime()) : null,
                order.getClosePrice(),
                order.getCloseTime() > 0L ? Instant.ofEpochMilli(order.getCloseTime()) : null,
                order.getProfitLossInPips(),
                message.getContent()
        );
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }
}
