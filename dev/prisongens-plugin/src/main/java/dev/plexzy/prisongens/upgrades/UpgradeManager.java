package dev.plexzy.prisongens.upgrades;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.utils.EconomyUtil;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

/**
 * Gestiona y almacena los datos de mejoras de todas las islas.
 */
public class UpgradeManager {

    private final PrisonGens plugin;
    private final Map<UUID, IslandUpgrades> upgradesMap = new ConcurrentHashMap<>();

    private File dataFile;
    private FileConfiguration dataConfig;

    public UpgradeManager(PrisonGens plugin) {
        this.plugin = plugin;
        loadData();
    }

    /**
     * Obtiene los datos de mejoras de una isla.
     * Si no existen, los crea con niveles en 0.
     */
    public IslandUpgrades getUpgrades(UUID islandId) {
        if (islandId == null) return null;
        return upgradesMap.computeIfAbsent(islandId, IslandUpgrades::new);
    }

    /**
     * Intenta mejorar una estadística específica de la isla del jugador.
     */
    public boolean purchaseUpgrade(Player player, UUID islandId, IslandUpgradeType type) {
        IslandUpgrades up = getUpgrades(islandId);
        if (up.isMaxLevel(type)) {
            player.sendMessage("§c✘ ¡Esta mejora ya está al nivel máximo!");
            return false;
        }

        int currentLevel = up.getLevel(type);
        double cost = type.getMoneyCost(currentLevel);
        long tCost = type.getTokenCost(currentLevel);

        if (!EconomyUtil.has(player, cost)) {
            player.sendMessage("§c✘ Necesitas §f$" + String.format("%.0f", cost) + " §cpara mejorar esto.");
            return false;
        }

        if (!plugin.getGenManager().hasTokens(player, tCost)) {
            player.sendMessage("§c✘ Necesitas §f" + tCost + " §cTokens para mejorar esto.");
            return false;
        }

        EconomyUtil.withdraw(player, cost);
        plugin.getGenManager().removeTokens(player, tCost);

        up.setLevel(type, currentLevel + 1);

        player.sendMessage("§a✔ Has mejorado §f" + type.getDisplayName() + " §aal nivel §f" + (currentLevel + 1) + "§a!");
        player.playSound(player.getLocation(), org.bukkit.Sound.ENTITY_PLAYER_LEVELUP, 1f, 1.2f);
        
        return true;
    }

    // ── Getters rápidos (Delegación) ──────────────────────────────────────────

    public int getRobotSlots(UUID islandId) {
        return getUpgrades(islandId).getRobotSlots();
    }

    // ── Persistencia ──────────────────────────────────────────────────────────

    private void loadData() {
        dataFile = new File(plugin.getDataFolder(), "upgrades.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) {
                plugin.getLogger().severe("No se pudo crear upgrades.yml");
            }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        for (String key : dataConfig.getKeys(false)) {
            try {
                UUID islandId = UUID.fromString(key);
                IslandUpgrades up = new IslandUpgrades(islandId);
                up.loadFromConfig(dataConfig.getConfigurationSection(key));
                upgradesMap.put(islandId, up);
            } catch (IllegalArgumentException e) {
                plugin.getLogger().warning("UUID de isla inválido en upgrades.yml: " + key);
            }
        }
    }

    public void saveAll() {
        for (String key : dataConfig.getKeys(false)) {
            dataConfig.set(key, null);
        }
        for (Map.Entry<UUID, IslandUpgrades> entry : upgradesMap.entrySet()) {
            entry.getValue().saveToConfig(dataConfig, entry.getKey().toString());
        }
        try {
            dataConfig.save(dataFile);
        } catch (IOException e) {
            plugin.getLogger().log(Level.SEVERE, "Error guardando upgrades.yml", e);
        }
    }
}
