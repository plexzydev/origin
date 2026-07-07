package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;

/**
 * Spawn Manager - Handles lobby spawn point.
 * Provides /setspawn command and auto-teleport on join.
 */
public class SpawnManager {

    private final LobbyCore plugin;
    private File dataFile;
    private FileConfiguration dataConfig;
    private Location spawnLocation;

    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 85, 85);
    private static final TextColor CYAN = TextColor.color(85, 255, 255);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);

    public SpawnManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadData();
    }

    private void loadData() {
        if (!plugin.getDataFolder().exists()) {
            plugin.getDataFolder().mkdirs();
        }
        dataFile = new File(plugin.getDataFolder(), "spawn.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);
        loadSpawnLocation();
    }

    private void loadSpawnLocation() {
        if (dataConfig.contains("spawn")) {
            String worldName = dataConfig.getString("spawn.world", "world");
            World world = Bukkit.getWorld(worldName);
            if (world != null) {
                double x = dataConfig.getDouble("spawn.x");
                double y = dataConfig.getDouble("spawn.y");
                double z = dataConfig.getDouble("spawn.z");
                float yaw = (float) dataConfig.getDouble("spawn.yaw");
                float pitch = (float) dataConfig.getDouble("spawn.pitch");
                spawnLocation = new Location(world, x, y, z, yaw, pitch);
            }
        }
    }

    /**
     * Set the lobby spawn point.
     */
    public void setSpawn(Location location) {
        spawnLocation = location.clone();

        dataConfig.set("spawn.world", location.getWorld().getName());
        dataConfig.set("spawn.x", location.getX());
        dataConfig.set("spawn.y", location.getY());
        dataConfig.set("spawn.z", location.getZ());
        dataConfig.set("spawn.yaw", location.getYaw());
        dataConfig.set("spawn.pitch", location.getPitch());

        try {
            dataConfig.save(dataFile);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    /**
     * Teleport a player to the lobby spawn.
     */
    public void teleportToSpawn(Player player) {
        if (spawnLocation != null) {
            player.teleport(spawnLocation);
        } else {
            // Fallback to world spawn
            player.teleport(player.getWorld().getSpawnLocation());
        }
    }

    /**
     * Check if spawn has been configured.
     */
    public boolean isSpawnSet() {
        return spawnLocation != null;
    }

    public Location getSpawnLocation() {
        return spawnLocation;
    }
}
