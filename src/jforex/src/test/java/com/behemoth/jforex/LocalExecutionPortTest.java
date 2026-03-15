package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.core.OrderEvent;
import com.behemoth.jforex.core.OrderEventType;
import com.behemoth.jforex.core.OrderRequest;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.local.LocalExecutionPort;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class LocalExecutionPortTest {
    @Test
    void fillsTriggeredStopOrderAndClosesAtEndOfReplay() {
        LocalExecutionPort port = new LocalExecutionPort();
        List<OrderEvent> events = new ArrayList<>();
        port.setEventListener(events::add);

        port.submitStopOrder(new OrderRequest(
                "GBPUSD",
                "ORDER1",
                OcoOrderPlan.Side.BUY,
                1.2502,
                1.0,
                0.01,
                Instant.parse("2025-07-07T00:15:00Z").toEpochMilli(),
                "test",
                Instant.parse("2025-07-07T00:00:00Z"),
                0.0001
        ));

        port.onTick(new RuntimeTick("GBPUSD", Instant.parse("2025-07-07T00:00:01Z"), 1.2500, 1.2501));
        port.onTick(new RuntimeTick("GBPUSD", Instant.parse("2025-07-07T00:00:02Z"), 1.2501, 1.2503));
        port.closeOpenOrdersAtEnd();

        assertThat(events).extracting(OrderEvent::type).containsExactly(
                OrderEventType.SUBMIT_OK,
                OrderEventType.FILL_OK,
                OrderEventType.CLOSE_OK
        );
        assertThat(events.get(1).openPrice()).isEqualTo(1.2503);
        assertThat(events.get(2).pnlPips()).isLessThan(0.0);
    }
}
