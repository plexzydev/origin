package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Map;

/**
 * EconomyManager - Handles 4 currencies:
 * - Money (dinero) - main currency from selling ores
 * - Tokens - from mining, used for enchants
 * - Coins (monedas) - premium/special currency
 * - Essences (esencias) - rare drops, used for top upgrades
 */
public class EconomyManager {

    private final PrisonGens plugin;
    private File dataFile;
    private FileConfiguration dataConfig;

    private final Map<UUID, double[]> balances = new ConcurrentHashMap<>();
    // Index: 0=money, 1=tokens, 2=coins, 3=essences

    public static final int MONEY = 0;
    public static final int TOKENS = 1;
    public static final int COINS = 2;
    public static final int ESSENCES = 3;

    public static final String[] CURRENCY_NAMES = {"Dinero", "Tokens", "Monedas", "Esencias"};
    public static final String[] CURRENCY_SYMBOLS = {"💰", "🔶", "🪙", "✧"};
    public static final String[] CURRENCY_COLORS = {"§a", "§6", "§e", "§d"};

    public EconomyManager(PrisonGens plugin) {
        this.plugin = plugin;
        loadData();
    }

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "economy.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        if (dataConfig.contains("players")) {
            var section = dataConfig.getConfigurationSection("players");
            if (section != null) {
                for (String uuidStr : section.getKeys(false)) {
                    UUID uuid = UUID.fromString(uuidStr);
                    double money = section.getDouble(uuidStr + ".money", 0);
                    double tokens = section.getDouble(uuidStr + ".tokens", 0);
                    double coins = section.getDouble(uuidStr + ".coins", 0);
                    double essences = section.getDouble(uuidStr + ".essences", 0);
                    balances.put(uuid, new double[]{money, tokens, coins, essences});
                }
            }
        }
    }

    public void saveData() {
        for (Map.Entry<UUID, double[]> entry : balances.entrySet()) {
            String path = "players." + entry.getKey().toString();
            double[] bal = entry.getValue();
            dataConfig.set(path + ".money", bal[MONEY]);
            dataConfig.set(path + ".tokens", bal[TOKENS]);
            dataConfig.set(path + ".coins", bal[COINS]);
            dataConfig.set(path + ".essences", bal[ESSENCES]);
        }
        try { dataConfig.save(dataFile); } catch (IOException e) { e.printStackTrace(); }
    }

    private double[] getOrCreate(UUID uuid) {
        return balances.computeIfAbsent(uuid, k -> new double[]{0, 0, 0, 0});
    }

    public double getBalance(Player player, int type) {
        return getOrCreate(player.getUniqueId())[type];
    }

    public double getBalance(UUID uuid, int type) {
        return getOrCreate(uuid)[type];
    }

    public void addBalance(Player player, int type, double amount) {
        getOrCreate(player.getUniqueId())[type] += amount;
    }

    public void addBalance(UUID uuid, int type, double amount) {
        getOrCreate(uuid)[type] += amount;
    }

    public boolean removeBalance(Player player, int type, double amount) {
        double[] bal = getOrCreate(player.getUniqueId());
        if (bal[type] < amount) return false;
        bal[type] -= amount;
        return true;
    }

    public void setBalance(Player player, int type, double amount) {
        getOrCreate(player.getUniqueId())[type] = amount;
    }

    public void setBalance(UUID uuid, int type, double amount) {
        getOrCreate(uuid)[type] = amount;
    }

    public String formatBalance(double amount) {
        if (amount >= 1_000_000_000) return String.format("%.1fB", amount / 1_000_000_000);
        if (amount >= 1_000_000) return String.format("%.1fM", amount / 1_000_000);
        if (amount >= 1_000) return String.format("%.1fK", amount / 1_000);
        return String.format("%.0f", amount);
    }
}
