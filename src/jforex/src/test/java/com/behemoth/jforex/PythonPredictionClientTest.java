package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.behemoth.jforex.runtime.PythonApiException;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.BackfillRequestPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.PredictRequestPayload;
import java.net.http.HttpClient;
import java.time.Instant;
import java.util.List;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;

class PythonPredictionClientTest {
    @Test
    void predictUsesCanonicalRiskOverrideFieldAndParsesResponse() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse().setBody("""
                    [{
                      "symbol": "GBPUSD",
                      "close_ts": "2025-07-07T00:00:00Z",
                      "candidate_uid": "oco|GBPUSD|100|h6|state_a",
                      "pred_prob": 0.78,
                      "threshold_exec": 0.61,
                      "selected_exec": 1,
                      "bar_ticks": 100,
                      "horizon": 6,
                      "barrier_pips": 2.0,
                      "cap_pips": 1.2,
                      "risk_blocked": false,
                      "risk_reservation_id": "rid-1"
                    }]
                    """).addHeader("Content-Type", "application/json"));
            PythonPredictionClient client = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());

            var response = client.predict(new PredictRequestPayload("GBPUSD", true, 10000.0, List.of(100), "run-1", null));

            assertThat(response).hasSize(1);
            assertThat(response.getFirst().candidateUid()).isEqualTo("oco|GBPUSD|100|h6|state_a");
            String requestBody = server.takeRequest().getBody().readUtf8();
            assertThat(requestBody).contains("\"risk_enabled_override\":true");
            assertThat(requestBody).doesNotContain("\"ftmo_enabled_override\"");
        }
    }

    @Test
    void surfacesStructuredApiErrors() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(422)
                    .setBody("{\"detail\":\"Insufficient warmup bars for GBPUSD\"}")
                    .addHeader("Content-Type", "application/json"));
            PythonPredictionClient client = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());

            assertThatThrownBy(() -> client.predict(new PredictRequestPayload("GBPUSD", true, 10000.0, List.of(100), "run-1", null)))
                    .isInstanceOf(PythonApiException.class)
                    .hasMessageContaining("Insufficient warmup bars");
        }
    }

    @Test
    void backfillSendsJsonBody() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("{\"ok\":true,\"symbol\":\"GBPUSD\"}")
                    .addHeader("Content-Type", "application/json"));
            PythonPredictionClient client = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());

            client.backfill(new BackfillRequestPayload(
                    "GBPUSD",
                    100,
                    List.of(new IncomingTickPayload(
                            "GBPUSD",
                            Instant.parse("2025-07-07T00:00:00Z"),
                            1.25,
                            1.2502,
                            1.0,
                            1L,
                            "run-1"
                    )),
                    "run-1"
            ));

            String requestBody = server.takeRequest().getBody().readUtf8();
            assertThat(requestBody).contains("\"symbol\":\"GBPUSD\"");
            assertThat(requestBody).contains("\"bar_ticks\":100");
            assertThat(requestBody).contains("\"ticks\":[");
        }
    }
}
