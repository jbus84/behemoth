package com.behemoth.jforex.live;

public final class BarAlignmentService {
    public int warmupKeepTickCount(int preCount, int warmupTicks, int alignTicks) {
        if (alignTicks <= 0) {
            throw new IllegalArgumentException("alignTicks must be > 0");
        }
        if (warmupTicks < 0) {
            throw new IllegalArgumentException("warmupTicks must be >= 0");
        }
        int remainder = Math.floorMod(preCount - warmupTicks, alignTicks);
        return warmupTicks + remainder;
    }
}
