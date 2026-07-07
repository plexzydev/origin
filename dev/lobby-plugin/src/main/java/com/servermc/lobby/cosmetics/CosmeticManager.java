package com.servermc.lobby.cosmetics;

import com.servermc.lobby.LobbyCore;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * CosmeticManager - Controls all active cosmetics per player.
 * Runs a global tick loop that updates every cosmetic effect.
 */
public class CosmeticManager {

    private final LobbyCore plugin;
    private BukkitTask tickTask;

    // Active cosmetics: player UUID -> list of active cosmetics
    private final Map<UUID, List<Cosmetic>> activeCosmetics = new ConcurrentHashMap<>();

    // Owned cosmetics: player UUID -> set of owned cosmetic types
    private final Map<UUID, Set<CosmeticType>> ownedCosmetics = new ConcurrentHashMap<>();

    public CosmeticManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadData();
    }

    /**
     * Start the global cosmetic tick loop (runs every 2 ticks = 10 times/second).
     */
    public void startTickLoop() {
        tickTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            for (Player player : Bukkit.getOnlinePlayers()) {
                List<Cosmetic> cosmetics = activeCosmetics.get(player.getUniqueId());
                if (cosmetics != null) {
                    for (Cosmetic cosmetic : cosmetics) {
                        try {
                            cosmetic.tick(player);
                        } catch (Exception e) {
                            plugin.getLogger().warning("[Cosmetics] Error ticking " + cosmetic.getType().name() + ": " + e.getMessage());
                        }
                    }
                }
            }
        }, 0L, 2L); // Every 2 ticks
    }

    public void stopTickLoop() {
        if (tickTask != null) tickTask.cancel();
        // Remove all pets
        for (Map.Entry<UUID, List<Cosmetic>> entry : activeCosmetics.entrySet()) {
            for (Cosmetic c : entry.getValue()) {
                if (c instanceof PetCosmetic pet) {
                    pet.removePet();
                }
            }
        }
        activeCosmetics.clear();
    }

    // ═══ Cosmetic Activation ═══

    /**
     * Toggle a cosmetic on/off for a player.
     */
    public boolean toggleCosmetic(Player player, CosmeticType type) {
        UUID uuid = player.getUniqueId();

        // Check if already active
        List<Cosmetic> current = activeCosmetics.computeIfAbsent(uuid, k -> new ArrayList<>());
        Optional<Cosmetic> existing = current.stream()
                .filter(c -> c.getType() == type)
                .findFirst();

        if (existing.isPresent()) {
            // Deactivate
            existing.get().unequip(player);
            current.remove(existing.get());
            saveActiveCosmetics(uuid);
            return false; // Now deactivated
        } else {
            // Remove any existing cosmetic of the same category
            current.removeIf(c -> {
                if (c.getType().getCategory() == type.getCategory()) {
                    c.unequip(player);
                    return true;
                }
                return false;
            });

            // Activate
            Cosmetic cosmetic = createCosmetic(type);
            cosmetic.equip(player);
            current.add(cosmetic);
            saveActiveCosmetics(uuid);
            return true; // Now activated
        }
    }

    /**
     * Remove all cosmetics from a player.
     */
    public void removeAllCosmetics(Player player) {
        UUID uuid = player.getUniqueId();
        List<Cosmetic> current = activeCosmetics.remove(uuid);
        if (current != null) {
            for (Cosmetic c : current) {
                c.unequip(player);
            }
            saveActiveCosmetics(uuid);
        }
    }

    /**
     * Cleanup cosmetics when player quits (does not overwrite save data).
     */
    public void cleanupOnQuit(Player player) {
        UUID uuid = player.getUniqueId();
        List<Cosmetic> current = activeCosmetics.remove(uuid);
        if (current != null) {
            for (Cosmetic c : current) {
                c.unequip(player);
            }
        }
    }

    /**
     * Check if a player has a specific cosmetic active.
     */
    public boolean isActive(Player player, CosmeticType type) {
        List<Cosmetic> current = activeCosmetics.get(player.getUniqueId());
        if (current == null) return false;
        return current.stream().anyMatch(c -> c.getType() == type);
    }

    /**
     * Get the active cosmetic type for a category (null if none).
     */
    public CosmeticType getActiveInCategory(Player player, CosmeticType.CosmeticCategory category) {
        List<Cosmetic> current = activeCosmetics.get(player.getUniqueId());
        if (current == null) return null;
        return current.stream()
                .filter(c -> c.getType().getCategory() == category)
                .map(Cosmetic::getType)
                .findFirst()
                .orElse(null);
    }

    // ═══ Ownership ═══

    /**
     * Check if a player owns a cosmetic.
     */
    public boolean ownsCosmetic(Player player, CosmeticType type) {
        if (type.getPrice() == 0) return true; // Free cosmetics
        Set<CosmeticType> owned = ownedCosmetics.get(player.getUniqueId());
        return owned != null && owned.contains(type);
    }

    /**
     * Give ownership of a cosmetic to a player.
     */
    public void grantCosmetic(Player player, CosmeticType type) {
        ownedCosmetics.computeIfAbsent(player.getUniqueId(), k -> new HashSet<>()).add(type);
        saveData();
    }

    /**
     * Purchase a cosmetic. Returns true if successful.
     */
    public boolean purchaseCosmetic(Player player, CosmeticType type) {
        if (ownsCosmetic(player, type)) return false; // Already owned
        
        int price = type.getPrice();
        if (price > 0) {
            if (!plugin.getCoinManager().removeCoins(player, price)) {
                return false; // Not enough coins
            }
            plugin.getCoinManager().saveData(); // Save coins immediately
        }
        grantCosmetic(player, type);
        return true;
    }

    // ═══ Factory ═══

    private Cosmetic createCosmetic(CosmeticType type) {
        return switch (type.getCategory()) {
            case PARTICLES -> new ParticleCosmetic(type);
            case PETS -> new PetCosmetic(type);
            case ARMOR -> new ArmorCosmetic(type);
        };
    }

    // ═══ Data Persistence ═══

    private void loadData() {
        // Load owned cosmetics
        if (plugin.getConfig().contains("cosmetics.owned")) {
            var section = plugin.getConfig().getConfigurationSection("cosmetics.owned");
            if (section != null) {
                for (String uuidStr : section.getKeys(false)) {
                    UUID uuid = UUID.fromString(uuidStr);
                    List<String> typeNames = section.getStringList(uuidStr);
                    Set<CosmeticType> owned = new HashSet<>();
                    for (String name : typeNames) {
                        try {
                            owned.add(CosmeticType.valueOf(name));
                        } catch (IllegalArgumentException ignored) {}
                    }
                    ownedCosmetics.put(uuid, owned);
                }
            }
        }
    }

    public void saveData() {
        // Save owned cosmetics
        for (Map.Entry<UUID, Set<CosmeticType>> entry : ownedCosmetics.entrySet()) {
            List<String> typeNames = entry.getValue().stream()
                    .map(CosmeticType::name)
                    .toList();
            plugin.getConfig().set("cosmetics.owned." + entry.getKey().toString(), typeNames);
        }

        // Save active cosmetics is handled individually on toggle
        plugin.saveConfig();
    }

    private void saveActiveCosmetics(UUID uuid) {
        List<Cosmetic> current = activeCosmetics.get(uuid);
        if (current == null || current.isEmpty()) {
            plugin.getConfig().set("cosmetics.active." + uuid.toString(), null);
        } else {
            List<String> typeNames = current.stream()
                    .map(c -> c.getType().name())
                    .toList();
            plugin.getConfig().set("cosmetics.active." + uuid.toString(), typeNames);
        }
        plugin.saveConfig();
    }

    public void restoreActiveCosmetics(Player player) {
        UUID uuid = player.getUniqueId();
        if (plugin.getConfig().contains("cosmetics.active." + uuid.toString())) {
            List<String> typeNames = plugin.getConfig().getStringList("cosmetics.active." + uuid.toString());
            for (String name : typeNames) {
                try {
                    CosmeticType type = CosmeticType.valueOf(name);
                    // Double check they actually own it
                    if (ownsCosmetic(player, type)) {
                        toggleCosmetic(player, type);
                    }
                } catch (IllegalArgumentException ignored) {}
            }
        }
    }
}
