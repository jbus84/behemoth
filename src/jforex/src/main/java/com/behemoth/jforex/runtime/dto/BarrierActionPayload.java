package com.behemoth.jforex.runtime.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record BarrierActionPayload(
        @JsonProperty("type") String type,
        @JsonProperty("symbol") String symbol,
        @JsonProperty("candidate_uid") String candidateUid,
        @JsonProperty("scan_id") String scanId,
        @JsonProperty("side") String side,
        @JsonProperty("reservation_id") String reservationId,
        @JsonProperty("broker_pos_id") String brokerPosId,
        @JsonProperty("blocked") boolean blocked,
        @JsonProperty("block_reason") String blockReason
) {
    public boolean isOpenMarket() {
        return "OPEN_MARKET".equals(type);
    }

    public boolean isCloseMarket() {
        return "CLOSE_MARKET".equals(type);
    }

    public boolean blocked() {
        return blocked;
    }
}
