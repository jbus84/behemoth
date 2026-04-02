package com.behemoth.jforex.runtime.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PredictResponsePayload(
        @JsonProperty("predictions") List<PredictionResponseItem> predictions,
        @JsonProperty("actions") List<BarrierActionPayload> actions
) {
    public PredictResponsePayload {
        if (predictions == null) predictions = List.of();
        if (actions == null) actions = List.of();
    }
}
