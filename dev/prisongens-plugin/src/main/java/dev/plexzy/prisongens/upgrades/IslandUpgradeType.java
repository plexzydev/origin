package dev.plexzy.prisongens.upgrades;

import org.bukkit.ChatColor;
import org.bukkit.Material;

public enum IslandUpgradeType {

    ISLAND_SIZE(
            "island_size",
            "§aTamaño de Isla",
            Material.GRASS_BLOCK,
            5,          // Max level
            100_000,    // Base cost money
            50_000,     // Base cost tokens
            "Expande los bordes físicos de tu isla."
    ),
    GEN_FEED_CAPACITY(
            "gen_feed",
            "§eCapacidad de Feeding",
            Material.GOLDEN_APPLE,
            10,
            25_000,
            10_000,
            "Aumenta cuántos generadores puedes introducir",
            "en el GEN principal."
    ),
    MAX_MEMBERS(
            "max_members",
            "§bMiembros de Isla",
            Material.PLAYER_HEAD,
            3,
            500_000,
            250_000,
            "Permite invitar a más jugadores a tu isla."
    ),
    SPAWNER_LIMIT(
            "spawner_limit",
            "§cLímite de Spawners",
            Material.SPAWNER,
            10,
            50_000,
            25_000,
            "Aumenta la cantidad de spawners que puedes colocar."
    ),
    HOPPER_LIMIT(
            "hopper_limit",
            "§7Límite de Tolvas",
            Material.HOPPER,
            10,
            20_000,
            10_000,
            "Aumenta la cantidad de tolvas permitidas."
    ),
    MINE_RESET_SPEED(
            "mine_speed",
            "§dReinicio de Mina",
            Material.CLOCK,
            10,
            75_000,
            35_000,
            "Reduce el tiempo que tarda la mina en reiniciarse."
    ),
    MINE_HEIGHT(
            "mine_height",
            "§6Profundidad de Mina",
            Material.DIAMOND_PICKAXE,
            5,
            150_000,
            75_000,
            "Añade más capas hacia abajo en tu mina."
    ),
    STORAGE_CAPACITY(
            "storage_cap",
            "§9Almacenamiento Virtual",
            Material.CHEST,
            20,
            10_000,
            5_000,
            "Aumenta la capacidad de almacenamiento de drops."
    ),
    ROBOT_SLOTS(
            "robot_slots",
            "§8Slots de Robots",
            Material.ARMOR_STAND,
            6,
            250_000,
            100_000,
            "Aumenta el número de robots activos en tu mina."
    ),
    MINE_SIZE_MULTIPLIER(
            "mine_size",
            "§3Área de Mina",
            Material.BEACON,
            5,
            500_000,
            200_000,
            "Expande el tamaño (largo y ancho) de tu mina."
    );

    private final String id;
    private final String coloredName;
    private final Material icon;
    private final int maxLevel;
    private final double baseMoneyCost;
    private final long baseTokenCost;
    private final String[] description;

    IslandUpgradeType(String id, String coloredName, Material icon,
                      int maxLevel, double baseMoneyCost, long baseTokenCost,
                      String... description) {
        this.id = id;
        this.coloredName = coloredName;
        this.icon = icon;
        this.maxLevel = maxLevel;
        this.baseMoneyCost = baseMoneyCost;
        this.baseTokenCost = baseTokenCost;
        this.description = description;
    }

    public String getId() { return id; }
    public String getColoredName() { return coloredName; }
    public String getDisplayName() { return ChatColor.stripColor(coloredName); }
    public Material getIcon() { return icon; }
    public int getMaxLevel() { return maxLevel; }

    public double getMoneyCost(int currentLevel) {
        return baseMoneyCost * Math.pow(1.8, currentLevel);
    }

    public long getTokenCost(int currentLevel) {
        return (long) (baseTokenCost * Math.pow(1.8, currentLevel));
    }

    public String getDescription() {
        return String.join("\n", description);
    }
}
