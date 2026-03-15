package com.behemoth.jforex.runtime;

/**
 * Structured HTTP/API failure raised by the Python runtime client.
 */
public final class PythonApiException extends RuntimeException {
    private final int statusCode;
    private final String detail;
    private final String responseBody;

    public PythonApiException(int statusCode, String detail, String responseBody) {
        super("Python API call failed with status=%d detail=%s".formatted(statusCode, detail));
        this.statusCode = statusCode;
        this.detail = detail == null ? "" : detail;
        this.responseBody = responseBody == null ? "" : responseBody;
    }

    public int statusCode() {
        return statusCode;
    }

    public String detail() {
        return detail;
    }

    public String responseBody() {
        return responseBody;
    }
}
