package com.servermc.prisongens.gen;

import org.bukkit.Material;
import org.bukkit.configuration.ConfigurationSection;

/**
 * Categorías de GEN. Los valores por defecto viven en el enum y
 * pueden sobreescribirse desde gens.yml.
 */
public enum GenCategory {

    INICIAL(1, "GEN Inicial", "§7", Material.COBBLESTONE, 10, 3, 100, 1000),
    HIERRO(2, "GEN de Hierro", "§f", Material.RAW_IRON, 15, 4, 250, 5000),
    ORO(3, "GEN de Oro", "§6", Material.RAW_GOLD, 20, 5, 600, 15000),
    DIAMANTE(4, "GEN de Diamante", "§b", Material.DIAMOND, 30, 6, 1500, 50000),
    ESMERALDA(5, "GEN de Esmeralda", "§a", Material.EMERALD, 40, 7, 4000, 150000),
    NETHERITE(6, "GEN de Netherite", "§4", Material.NETHERITE_SCRAP, 60, 8, 10000, 500000);

    public int tier;
    public String display;
    public String color;
    public Material icon;
    public int baseFeedCapacity;
    public int maxStage;
    public int feedBaseXp;
    public long price;

    GenCategory(int tier, String display, String color, Material icon,
                int baseFeedCapacity, int maxStage, int feedBaseXp, long price) {
        this.tier = tier;
        this.display = display;
        this.color = color;
        this.icon = icon;
        this.baseFeedCapacity = baseFeedCapacity;
        this.maxStage = maxStage;
        this.feedBaseXp = feedBaseXp;
        this.price = price;
    }

    /** Aplica overrides de gens.yml (sección categories.<NOMBRE>). */
    public void applyConfig(ConfigurationSection sec) {
        if (sec == null) return;
        tier = sec.getInt("tier", tier);
        display = sec.getString("display", display);
        color = sec.getString("color", color);
        try {
            String iconName = sec.getString("icon");
            if (iconName != null) icon = Material.valueOf(iconName.toUpperCase());
        } catch (IllegalArgumentException ignored) {}
        baseFeedCapacity = sec.getInt("base-feed-capacity", baseFeedCapacity);
        maxStage = sec.getInt("max-stage", maxStage);
        feedBaseXp = sec.getInt("feed-base-xp", feedBaseXp);
        price = sec.getLong("price", price);
    }

    public static GenCategory fromString(String name) {
        if (name == null) return null;
        try { return valueOf(name.toUpperCase()); } catch (IllegalArgumentException e) { return null; }
    }
}
