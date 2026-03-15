package com.behemoth.jforex.core;

import java.util.Objects;

public record RuntimeInstrument(
        String symbol,
        double pipSize
) {
    public RuntimeInstrument {
        symbol = normalizeSymbol(symbol);
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (pipSize <= 0.0) {
            throw new IllegalArgumentException("pipSize must be > 0");
        }
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }
}
