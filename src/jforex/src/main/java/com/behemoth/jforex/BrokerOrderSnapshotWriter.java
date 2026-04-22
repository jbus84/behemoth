package com.behemoth.jforex;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class BrokerOrderSnapshotWriter {
    private final Path target;
    private final ObjectMapper objectMapper;

    BrokerOrderSnapshotWriter(Path target, ObjectMapper objectMapper) {
        this.target = Objects.requireNonNull(target, "target");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
    }

    synchronized void write(Instant capturedAtUtc, List<BrokerSnapshotOrder> orders) {
        Objects.requireNonNull(capturedAtUtc, "capturedAtUtc");
        Objects.requireNonNull(orders, "orders");
        Path parent = target.getParent();
        if (parent == null) {
            throw new IllegalArgumentException("target must have a parent directory");
        }
        try {
            Files.createDirectories(parent);
            Path tmp = Files.createTempFile(parent, target.getFileName().toString(), ".tmp");
            try {
                String json = objectMapper.writeValueAsString(toJson(capturedAtUtc, orders));
                Files.writeString(tmp, json, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
                Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } finally {
                Files.deleteIfExists(tmp);
            }
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to write broker snapshot: " + target, exc);
        }
    }

    private Map<String, Object> toJson(Instant capturedAtUtc, List<BrokerSnapshotOrder> orders) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("captured_at_utc", capturedAtUtc.toString());
        root.put(
                "orders",
                orders.stream().map(order -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("order_id", order.orderId());
                    item.put("label", order.label());
                    item.put("symbol", order.symbol());
                    item.put("state", order.state());
                    item.put("order_command", order.orderCommand());
                    return item;
                }).toList()
        );
        return root;
    }

    record BrokerSnapshotOrder(
            String orderId,
            String label,
            String symbol,
            String state,
            String orderCommand
    ) {
    }
}
