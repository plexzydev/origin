package dev.plexzy.prisongens.robots;

import org.bukkit.ChatColor;
import org.bukkit.Material;

/**
 * Define las categorías de Robot disponibles.
 * Cada categoría tiene stats base distintos.
 */
public enum RobotCategory {

    WOODEN(
            "Madera",
            ChatColor.GRAY,
            Material.OAK_PLANKS,
            1,          // customModelData
            0.5,        // baseEfficiency  (multiplicador de recursos)
            1.0,        // baseSpeed       (acciones por segundo)
            3,          // baseRadius      (bloques alrededor del robot)
            64,         // baseStorage     (items que guarda internamente)
            5_000,      // tokenMultiplier (base tokens por acción)
            50          // moneyPerAction
    ),
    STONE(
            "Piedra",
            ChatColor.WHITE,
            Material.STONE,
            2,
            0.75,
            1.5,
            4,
            128,
            10_000,
            100
    ),
    IRON(
            "Hierro",
            ChatColor.AQUA,
            Material.IRON_INGOT,
            3,
            1.0,
            2.0,
            5,
            256,
            25_000,
            250
    ),
    GOLD(
            "Oro",
            ChatColor.YELLOW,
            Material.GOLD_INGOT,
            4,
            1.5,
            2.5,
            6,
            512,
            50_000,
            500
    ),
    DIAMOND(
            "Diamante",
            ChatColor.DARK_AQUA,
            Material.DIAMOND,
            5,
            2.0,
            3.0,
            7,
            1024,
            100_000,
            1_000
    ),
    EMERALD(
            "Esmeralda",
            ChatColor.GREEN,
            Material.EMERALD,
            6,
            3.0,
            4.0,
            9,
            2048,
            250_000,
            2_500
    ),
    NETHERITE(
            "Netherite",
            ChatColor.DARK_RED,
            Material.NETHERITE_INGOT,
            7,
            5.0,
            5.0,
            12,
            4096,
            500_000,
            5_000
    ),
    LEGENDARY(
            "Legendario",
            ChatColor.GOLD,
            Material.NETHER_STAR,
            8,
            10.0,
            8.0,
            16,
            8192,
            1_000_000,
            10_000
    );

    private final String displayName;
    private final ChatColor color;
    private final Material displayMaterial;
    private final int customModelData;
    private final double baseEfficiency;
    private final double baseSpeed;
    private final int baseRadius;
    private final int baseStorage;
    private final long baseTokensPerAction;
    private final double baseMoneyPerAction;

    RobotCategory(String displayName, ChatColor color, Material displayMaterial,
                  int customModelData, double baseEfficiency, double baseSpeed,
                  int baseRadius, int baseStorage, long baseTokensPerAction,
                  double baseMoneyPerAction) {
        this.displayName       = displayName;
        this.color             = color;
        this.displayMaterial   = displayMaterial;
        this.customModelData   = customModelData;
        this.baseEfficiency    = baseEfficiency;
        this.baseSpeed         = baseSpeed;
        this.baseRadius        = baseRadius;
        this.baseStorage       = baseStorage;
        this.baseTokensPerAction = baseTokensPerAction;
        this.baseMoneyPerAction = baseMoneyPerAction;
    }

    public String getDisplayName()       { return displayName; }
    public ChatColor getColor()          { return color; }
    public Material getDisplayMaterial() { return displayMaterial; }
    public int getCustomModelData()      { return customModelData; }
    public double getBaseEfficiency()    { return baseEfficiency; }
    public double getBaseSpeed()         { return baseSpeed; }
    public int getBaseRadius()           { return baseRadius; }
    public int getBaseStorage()          { return baseStorage; }
    public long getBaseTokensPerAction() { return baseTokensPerAction; }
    public double getBaseMoneyPerAction(){ return baseMoneyPerAction; }

    public String getColoredName() {
        return color + "✦ " + displayName;
    }

    /**
     * Experiencia necesaria para subir al siguiente nivel (fórmula escalable).
     */
    public long xpToLevel(int level) {
        return (long) (100 * Math.pow(level, 1.8) * (ordinal() + 1));
    }
}
