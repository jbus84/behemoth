package com.behemoth.jforex.adapter;

import com.behemoth.jforex.domain.PredictionDecision;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Objects;

/**
 * Reproduces the current cBot OCO mapping: two opposite stop-limit entries
 * around the live bid/ask with a shared group label and identical stop-limit cap.
 */
public final class OcoOrderPlanner {
    private static final DateTimeFormatter LABEL_TS =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss").withZone(ZoneOffset.UTC);
    private static final int LABEL_MAX_LEN = 256;

    private OcoOrderPlanner() {
    }

    public static OcoOrderPlan build(
            PredictionDecision decision,
            double bid,
            double ask,
            double pipSize,
            Instant placedAtUtc
    ) {
        Objects.requireNonNull(decision, "decision");
        Objects.requireNonNull(placedAtUtc, "placedAtUtc");
        if (bid <= 0.0 || ask <= 0.0 || ask < bid) {
            throw new IllegalArgumentException("invalid bid/ask inputs");
        }
        if (pipSize <= 0.0) {
            throw new IllegalArgumentException("pipSize must be > 0");
        }

        double offset = decision.barrierPips() * pipSize;
        double buyTrigger = ask + offset;
        double sellTrigger = bid - offset;
        String ts = LABEL_TS.format(placedAtUtc);
        String rid = sanitizeToken(decision.reservationId().isBlank() ? "NA" : decision.reservationId(), 16);
        String symbol = sanitizeToken(decision.symbol(), 12);
        String candidateToken = candidateToken(decision.candidateUid());
        String groupLabel = trimLabel(
                "OCO_" + symbol
                        + "_T" + decision.barTicks()
                        + "_H" + decision.horizon()
                        + "_TS" + ts
                        + "_RID" + rid
                        + "_CID" + candidateToken
        );
        String baseComment =
                "candidate_uid=" + decision.candidateUid()
                        + ";reservation_id=" + (decision.reservationId().isBlank() ? "NA" : decision.reservationId())
                        + ";bar_ticks=" + decision.barTicks()
                        + ";horizon=" + decision.horizon()
                        + ";placed_at_utc=" + placedAtUtc;

        return new OcoOrderPlan(
                groupLabel,
                new OcoOrderPlan.EntryLeg(
                        trimLabel(groupLabel + "_BUY"),
                        OcoOrderPlan.Side.BUY,
                        buyTrigger,
                        baseComment + ";leg=BUY"
                ),
                new OcoOrderPlan.EntryLeg(
                        trimLabel(groupLabel + "_SELL"),
                        OcoOrderPlan.Side.SELL,
                        sellTrigger,
                        baseComment + ";leg=SELL"
                ),
                decision.capPips()
        );
    }

    public static boolean requiresManualSiblingCancel(boolean nativeOcoSupported) {
        return true;
    }

    private static String sanitizeToken(String raw, int maxLen) {
        StringBuilder out = new StringBuilder();
        for (char ch : raw.toCharArray()) {
            if ((ch >= 'A' && ch <= 'Z')
                    || (ch >= 'a' && ch <= 'z')
                    || (ch >= '0' && ch <= '9')) {
                out.append(ch);
            } else {
                out.append('_');
            }
            if (out.length() >= maxLen) {
                break;
            }
        }
        if (out.isEmpty()) {
            return "NA";
        }
        return out.toString().toUpperCase();
    }

    private static String candidateToken(String candidateUid) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(candidateUid.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                hex.append(String.format("%02x", bytes[i]));
            }
            return hex.toString().toUpperCase();
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256 unavailable", exc);
        }
    }

    private static String trimLabel(String label) {
        if (label.length() <= LABEL_MAX_LEN) {
            return label;
        }
        return label.substring(0, LABEL_MAX_LEN);
    }
}
