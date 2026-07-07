package dev.plexzy.prisongens.robots;

public enum RobotStat {

    SPEED("⚡ Velocidad", 5_000, 2_500) {
        @Override public void apply(RobotData r) { r.setSpeed(r.getSpeed() + 0.1); }
    },
    RADIUS("🔍 Radio", 8_000, 4_000) {
        @Override public void apply(RobotData r) { r.setRadius(r.getRadius() + 1); }
    },
    STORAGE("📦 Almacenamiento", 3_000, 1_500) {
        @Override public void apply(RobotData r) { r.setStorage(r.getStorage() + 64); }
    },
    EFFICIENCY("⚙ Eficiencia", 12_000, 6_000) {
        @Override public void apply(RobotData r) { r.setEfficiency(r.getEfficiency() + 0.1); }
    },
    MONEY_BOOST("💰 Dinero/tick", 15_000, 7_500) {
        @Override public void apply(RobotData r) {
            r.setMoneyPerAction(r.getMoneyPerAction() * 1.1);
        }
    },
    TOKEN_BOOST("🪙 Tokens/tick", 15_000, 7_500) {
        @Override public void apply(RobotData r) {
            r.setTokensPerAction((long) (r.getTokensPerAction() * 1.1));
        }
    };

    private final String displayName;
    private final double baseCost;
    private final long baseTokenCost;

    RobotStat(String displayName, double baseCost, long baseTokenCost) {
        this.displayName   = displayName;
        this.baseCost      = baseCost;
        this.baseTokenCost = baseTokenCost;
    }

    public abstract void apply(RobotData robot);

    public double getCost(int tier)    { return baseCost  * Math.pow(1.5, tier); }
    public long getTokenCost(int tier) { return (long) (baseTokenCost * Math.pow(1.5, tier)); }
    public String getDisplayName()     { return displayName; }
}
