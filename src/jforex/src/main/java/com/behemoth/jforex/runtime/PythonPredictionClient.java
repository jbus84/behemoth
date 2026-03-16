package com.behemoth.jforex.runtime;

import com.behemoth.jforex.runtime.dto.AccountSnapshotRequestPayload;
import com.behemoth.jforex.runtime.dto.ActiveTradePayload;
import com.behemoth.jforex.runtime.dto.ApiAckResponse;
import com.behemoth.jforex.runtime.dto.BackfillRequestPayload;
import com.behemoth.jforex.runtime.dto.FeedStatusResponsePayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.PredictRequestPayload;
import com.behemoth.jforex.runtime.dto.PredictionResponseItem;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.behemoth.jforex.runtime.dto.TickBatchResponsePayload;
import com.behemoth.jforex.runtime.dto.TickIngestResponsePayload;
import com.behemoth.jforex.runtime.dto.TradeOpenRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeTouchRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeUpdateRequestPayload;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Thin HTTP client for the Python decision engine.
 *
 * This intentionally stays broker-agnostic; JForex feeds ticks and receives
 * execution intents from the existing FastAPI runtime.
 */
public final class PythonPredictionClient {
    private static final Duration MIN_TICK_BATCH_TIMEOUT = Duration.ofMinutes(10);

    private final HttpClient httpClient;
    private final HttpClient tickBatchHttpClient;
    private final URI apiBaseUri;
    private final ObjectMapper objectMapper;
    private final Duration requestTimeout;
    private final Duration tickBatchTimeout;

    public PythonPredictionClient(HttpClient httpClient, URI apiBaseUri) {
        this(httpClient, apiBaseUri, buildObjectMapper(), Duration.ofSeconds(60));
    }

    public PythonPredictionClient(HttpClient httpClient, URI apiBaseUri, Duration requestTimeout) {
        this(httpClient, apiBaseUri, buildObjectMapper(), requestTimeout);
    }

    public PythonPredictionClient(HttpClient httpClient, URI apiBaseUri, Duration requestTimeout, Duration tickBatchTimeout) {
        this(httpClient, apiBaseUri, buildObjectMapper(), requestTimeout, tickBatchTimeout);
    }

    public PythonPredictionClient(HttpClient httpClient, URI apiBaseUri, ObjectMapper objectMapper) {
        this(httpClient, apiBaseUri, objectMapper, Duration.ofSeconds(60));
    }

    public PythonPredictionClient(HttpClient httpClient, URI apiBaseUri, ObjectMapper objectMapper, Duration requestTimeout) {
        this(httpClient, apiBaseUri, objectMapper, requestTimeout, maxTickBatchTimeout(requestTimeout));
    }

    public PythonPredictionClient(
            HttpClient httpClient,
            URI apiBaseUri,
            ObjectMapper objectMapper,
            Duration requestTimeout,
            Duration tickBatchTimeout
    ) {
        this.httpClient = Objects.requireNonNull(httpClient, "httpClient");
        this.tickBatchHttpClient = buildTickBatchHttpClient(tickBatchTimeout);
        this.apiBaseUri = Objects.requireNonNull(apiBaseUri, "apiBaseUri");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
        this.requestTimeout = Objects.requireNonNull(requestTimeout, "requestTimeout");
        this.tickBatchTimeout = Objects.requireNonNull(tickBatchTimeout, "tickBatchTimeout");
    }

    public ApiAckResponse accountSnapshot(AccountSnapshotRequestPayload request) {
        return sendJson("POST", "/risk/account/snapshot", request, ApiAckResponse.class);
    }

    public ApiAckResponse backfill(BackfillRequestPayload request) {
        return sendJson("POST", "/backfill", request, ApiAckResponse.class);
    }

    public TickBatchResponsePayload tickBatch(TickBatchRequestPayload request) {
        return sendJson("POST", "/ticks/batch", request, TickBatchResponsePayload.class, tickBatchTimeout);
    }

    public TickIngestResponsePayload tick(IncomingTickPayload request) {
        return sendJson("POST", "/ticks", request, TickIngestResponsePayload.class, tickBatchTimeout);
    }

    public List<PredictionResponseItem> predict(PredictRequestPayload request) {
        return sendJsonList("POST", "/predict", request, new TypeReference<>() {
        });
    }

    public ApiAckResponse openTrade(TradeOpenRequestPayload request) {
        return sendJson("POST", "/trades/open", request, ApiAckResponse.class);
    }

    public ApiAckResponse touchTrade(TradeTouchRequestPayload request) {
        return sendJson("POST", "/trades/touch", request, ApiAckResponse.class);
    }

    public ApiAckResponse updateTrade(TradeUpdateRequestPayload request) {
        return sendJson("POST", "/trades/update", request, ApiAckResponse.class);
    }

    public FeedStatusResponsePayload feedStatus() {
        return sendJson("GET", "/runtime/feed/status", null, FeedStatusResponsePayload.class);
    }

    public List<ActiveTradePayload> activeTrades(String symbol) {
        String encoded = URLEncoder.encode(symbol, StandardCharsets.UTF_8);
        return sendJsonList("GET", "/trades/active?symbol=" + encoded, null, new TypeReference<>() {
        });
    }

    public ObjectMapper objectMapper() {
        return objectMapper;
    }

    private <T> T sendJson(String method, String path, Object payload, Class<T> responseType) {
        return sendJson(method, path, payload, responseType, requestTimeout);
    }

    private <T> T sendJson(String method, String path, Object payload, Class<T> responseType, Duration timeout) {
        HttpRequest request = buildRequest(method, path, payload, timeout);
        try {
            HttpResponse<String> response = selectHttpClient(path, timeout).send(request, HttpResponse.BodyHandlers.ofString());
            ensureSuccess(response);
            if (responseType == Void.class || response.body() == null || response.body().isBlank()) {
                return null;
            }
            return objectMapper.readValue(response.body(), responseType);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new PythonApiException(599, "interrupted", "");
        } catch (IOException exc) {
            throw new PythonApiException(599, exc.getMessage(), "");
        }
    }

    private <T> T sendJsonList(String method, String path, Object payload, TypeReference<T> typeReference) {
        HttpRequest request = buildRequest(method, path, payload, requestTimeout);
        try {
            HttpResponse<String> response = selectHttpClient(path, requestTimeout).send(request, HttpResponse.BodyHandlers.ofString());
            ensureSuccess(response);
            return objectMapper.readValue(response.body(), typeReference);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new PythonApiException(599, "interrupted", "");
        } catch (IOException exc) {
            throw new PythonApiException(599, exc.getMessage(), "");
        }
    }

    private HttpRequest buildRequest(String method, String path, Object payload, Duration timeout) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(apiBaseUri.resolve(path))
                .timeout(timeout)
                .version(HttpClient.Version.HTTP_1_1)
                .header("Accept", "application/json");
        if ("GET".equalsIgnoreCase(method)) {
            return builder.GET().build();
        }
        try {
            String body = payload == null ? "" : objectMapper.writeValueAsString(payload);
            return builder.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(body))
                    .build();
        } catch (JsonProcessingException exc) {
            throw new PythonApiException(500, exc.getMessage(), "");
        }
    }

    private void ensureSuccess(HttpResponse<String> response) throws JsonProcessingException {
        if (response.statusCode() >= 200 && response.statusCode() < 300) {
            return;
        }
        String body = response.body();
        String detail = body;
        if (body != null && !body.isBlank()) {
            try {
                Map<String, Object> parsed = objectMapper.readValue(body, new TypeReference<>() {
                });
                if (parsed.get("detail") != null) {
                    detail = String.valueOf(parsed.get("detail"));
                }
            } catch (Exception ignored) {
                detail = body;
            }
        }
        throw new PythonApiException(response.statusCode(), detail, body);
    }

    private static ObjectMapper buildObjectMapper() {
        return new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    private HttpClient selectHttpClient(String path, Duration timeout) {
        if (!"/ticks/batch".equals(path)) {
            return httpClient;
        }
        return tickBatchHttpClient;
    }

    private static Duration maxTickBatchTimeout(Duration requestTimeout) {
        return requestTimeout.compareTo(MIN_TICK_BATCH_TIMEOUT) >= 0
                ? requestTimeout
                : MIN_TICK_BATCH_TIMEOUT;
    }

    private static HttpClient buildTickBatchHttpClient(Duration timeout) {
        return HttpClient.newBuilder()
                .connectTimeout(timeout)
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }
}
