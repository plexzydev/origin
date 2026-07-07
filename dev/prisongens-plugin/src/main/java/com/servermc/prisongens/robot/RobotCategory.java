package com.servermc.prisongens.robot;

import org.bukkit.Material;
import org.bukkit.configuration.ConfigurationSection;

/**
 * Categorías de Robot. Los valores por defecto viven en el enum y
 * pueden sobreescribirse desde robots.yml (sección categories.<NOMBRE>).
 */
public enum RobotCategory {

    COMUN(1, "Robot Común", "§7", Material.IRON_GOLEM_SPAWN_EGG, 5.0, 0.02, 25, 500, 5000),
    RARO(2, "Robot Raro", "§9", Material.IRON_GOLEM_SPAWN_EGG, 15.0, 0.04, 40, 1500, 25000),
    EPICO(3, "Robot Épico", "§5", Material.IRON_GOLEM_SPAWN_EGG, 45.0, 0.08, 60, 5000, 100000),
    LEGENDARIO(4, "Robot Legendario", "§6", Material.IRON_GOLEM_SPAWN_EGG, 120.0, 0.15, 80, 15000, 400000),
    MITICO(5, "Robot Mítico", "§c", Material.IRON_GOLEM_SPAWN_EGG, 300.0, 0.25, 100, 50000, 1500000);

    public int tier;
    public String display;
    public String color;
    public Material icon;
    public double moneyPerSec;
    public double tokenChance;
    public int maxLevel;
    public long upgradeBaseCost;
    public long price;

    RobotCategory(int tier, String display, String color, Material icon,
                  double moneyPerSec, double tokenChance, int maxLevel,
                  long upgradeBaseCost, long price) {
        this.tier = tier;
        this.display = display;
        this.color = color;
        this.icon = icon;
        this.moneyPerSec = moneyPerSec;
        this.tokenChance = tokenChance;
        this.maxLevel = maxLevel;
        this.upgradeBaseCost = upgradeBaseCost;
        this.price = price;
    }

    /** Aplica overrides de robots.yml (sección categories.<NOMBRE>). */
    public void applyConfig(ConfigurationSection sec) {
        if (sec == null) return;
        tier = sec.getInt("tier", tier);
        display = sec.getString("display", display);
        color = sec.getString("color", color);
        try {
            String iconName = sec.getString("icon");
            if (iconName != null) icon = Material.valueOf(iconName.toUpperCase());
        } catch (IllegalArgumentException ignored) {}
        moneyPerSec = sec.getDouble("base-money-per-sec", moneyPerSec);
        tokenChance = sec.getDouble("base-token-chance", tokenChance);
        maxLevel = sec.getInt("max-level", maxLevel);
        upgradeBaseCost = sec.getLong("upgrade-base-cost", upgradeBaseCost);
        price = sec.getLong("price", price);
    }

    public static RobotCategory fromString(String name) {
        if (name == null) return null;
        try { return valueOf(name.toUpperCase()); } catch (IllegalArgumentException e) { return null; }
    }
}
