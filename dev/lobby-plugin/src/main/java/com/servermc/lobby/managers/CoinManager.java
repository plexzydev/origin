package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * CoinManager - Manages lobby coins for players.
 * Coins can be used to buy cosmetics.
 */
public class CoinManager {

    private final LobbyCore plugin;
    private final Map<UUID, Integer> coins = new ConcurrentHashMap<>();
    private final File dataFile;
    private FileConfiguration dataConfig;

    public CoinManager(LobbyCore plugin) {
        this.plugin = plugin;
        this.dataFile = new File(plugin.getDataFolder(), "coins.yml");
        loadData();
    }

    /**
     * Get the coin balance for a player.
     */
    public int getCoins(Player player) {
        return coins.getOrDefault(player.getUniqueId(), 0);
    }

    /**
     * Get the coin balance by UUID.
     */
    public int getCoins(UUID uuid) {
        return coins.getOrDefault(uuid, 0);
    }

    /**
     * Set coins for a player.
     */
    public void setCoins(Player player, int amount) {
        coins.put(player.getUniqueId(), Math.max(0, amount));
    }

    /**
     * Add coins to a player.
     */
    public void addCoins(Player player, int amount) {
        int current = getCoins(player);
        coins.put(player.getUniqueId(), current + amount);
    }

    /**
     * Add coins by UUID.
     */
    public void addCoins(UUID uuid, int amount) {
        int current = coins.getOrDefault(uuid, 0);
        coins.put(uuid, current + amount);
    }

    /**
     * Remove coins from a player. Returns true if they had enough.
     */
    public boolean removeCoins(Player player, int amount) {
        int current = getCoins(player);
        if (current < amount) return false;
        coins.put(player.getUniqueId(), current - amount);
        return true;
    }

    /**
     * Check if a player has enough coins.
     */
    public boolean hasEnough(Player player, int amount) {
        return getCoins(player) >= amount;
    }

    // ═══ Persistence ═══

    public void loadData() {
        if (!dataFile.exists()) {
            try {
                dataFile.getParentFile().mkdirs();
                dataFile.createNewFile();
            } catch (IOException e) {
                plugin.getLogger().warning("[CoinManager] Error creating coins.yml: " + e.getMessage());
            }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        if (dataConfig.contains("coins")) {
            var section = dataConfig.getConfigurationSection("coins");
            if (section != null) {
                for (String key : section.getKeys(false)) {
                    try {
                        UUID uuid = UUID.fromString(key);
                        coins.put(uuid, section.getInt(key));
                    } catch (IllegalArgumentException ignored) {}
                }
            }
        }
    }

    public void saveData() {
        for (Map.Entry<UUID, Integer> entry : coins.entrySet()) {
            dataConfig.set("coins." + entry.getKey().toString(), entry.getValue());
        }
        try {
            dataConfig.save(dataFile);
        } catch (IOException e) {
            plugin.getLogger().warning("[CoinManager] Error saving coins.yml: " + e.getMessage());
        }
    }
}
