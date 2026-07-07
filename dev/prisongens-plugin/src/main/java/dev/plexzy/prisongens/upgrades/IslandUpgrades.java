package dev.plexzy.prisongens.upgrades;

import org.bukkit.configuration.ConfigurationSection;

import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;

/**
 * Almacena el nivel actual de cada mejora de una isla específica.
 */
public class IslandUpgrades {

    private final UUID islandId;
    private final Map<IslandUpgradeType, Integer> levels = new EnumMap<>(IslandUpgradeType.class);

    public IslandUpgrades(UUID islandId) {
        this.islandId = islandId;
        // Inicializar todos los niveles en 0
        for (IslandUpgradeType type : IslandUpgradeType.values()) {
            levels.put(type, 0);
        }
    }

    public int getLevel(IslandUpgradeType type) {
        return levels.getOrDefault(type, 0);
    }

    public void setLevel(IslandUpgradeType type, int level) {
        levels.put(type, Math.max(0, Math.min(level, type.getMaxLevel())));
    }

    public boolean isMaxLevel(IslandUpgradeType type) {
        return getLevel(type) >= type.getMaxLevel();
    }

    // ── Valores calculados ─────────────────────────────────────────────────

    /** Tamaño base de isla (bloques). Comienza en 64, +16 por nivel. */
    public int getIslandSize() {
        return 64 + getLevel(IslandUpgradeType.ISLAND_SIZE) * 16;
    }

    /** Capacidad de feeding del GEN. Comienza en 10, +5 por nivel. */
    public int getGenFeedCapacity() {
        return 10 + getLevel(IslandUpgradeType.GEN_FEED_CAPACITY) * 5;
    }

    /** Máximo de miembros. Comienza en 2, +1 por nivel. */
    public int getMaxMembers() {
        return 2 + getLevel(IslandUpgradeType.MAX_MEMBERS);
    }

    /** Límite de spawners. Comienza en 5, +3 por nivel. */
    public int getSpawnerLimit() {
        return 5 + getLevel(IslandUpgradeType.SPAWNER_LIMIT) * 3;
    }

    /** Límite de hoppers. Comienza en 10, +5 por nivel. */
    public int getHopperLimit() {
        return 10 + getLevel(IslandUpgradeType.HOPPER_LIMIT) * 5;
    }

    /** Velocidad de reinicio (segundos). Comienza en 60, -5 por nivel. */
    public int getMineResetSpeed() {
        return Math.max(10, 60 - getLevel(IslandUpgradeType.MINE_RESET_SPEED) * 5);
    }

    /** Altura de mina. Comienza en 20, +5 por nivel. */
    public int getMineHeight() {
        return 20 + getLevel(IslandUpgradeType.MINE_HEIGHT) * 5;
    }

    /** Capacidad de almacenamiento. Comienza en 5000, +2500 por nivel. */
    public long getStorageCapacity() {
        return 5000 + getLevel(IslandUpgradeType.STORAGE_CAPACITY) * 2500L;
    }

    /** Slots de robots. Comienza en 1, +1 por nivel. */
    public int getRobotSlots() {
        return 1 + getLevel(IslandUpgradeType.ROBOT_SLOTS);
    }

    /** Multiplicador de mina (área base = 5x5, +2 por nivel -> 5, 7, 9, 11...). */
    public int getMineSize() {
        return 5 + getLevel(IslandUpgradeType.MINE_SIZE_MULTIPLIER) * 2;
    }

    // ── Serialización ────────────────────────────────────────────────────────
    
    public void saveToConfig(ConfigurationSection cfg, String path) {
        for (Map.Entry<IslandUpgradeType, Integer> entry : levels.entrySet()) {
            cfg.set(path + "." + entry.getKey().name(), entry.getValue());
        }
    }

    public void loadFromConfig(ConfigurationSection cfg) {
        if (cfg == null) return;
        for (IslandUpgradeType type : IslandUpgradeType.values()) {
            if (cfg.contains(type.name())) {
                levels.put(type, cfg.getInt(type.name()));
            }
        }
    }

    public UUID getIslandId() {
        return islandId;
    }
}
