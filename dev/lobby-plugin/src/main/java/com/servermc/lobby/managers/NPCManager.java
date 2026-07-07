package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.npc.FakePlayerNPC;
import com.servermc.lobby.utils.ProxyUtils;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;
import org.bukkit.entity.Villager;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * NPC Manager - Real player-body NPCs with skins and holograms.
 */
public class NPCManager {

    private final LobbyCore plugin;
    private File dataFile;
    private FileConfiguration dataConfig;

    // npcId -> FakePlayerNPC
    private final Map<String, FakePlayerNPC> fakePlayerMap = new ConcurrentHashMap<>();
    // npcId -> hologram entities
    private final Map<String, List<Entity>> holoMap = new ConcurrentHashMap<>();
    // entityId (NMS) -> npcId (for click detection)
    private final Map<Integer, String> entityIdMap = new ConcurrentHashMap<>();
    // npcId -> location (for click proximity detection)
    private final Map<String, Location> npcLocations = new ConcurrentHashMap<>();

    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);
    private static final TextColor ORANGE = TextColor.color(255, 140, 0);

    public NPCManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadData();
    }

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "npcs.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);
    }

    public boolean createNPC(String id, String displayName, String serverName, Location location, String skin) {
        if (dataConfig.contains("npcs." + id)) return false;
        String path = "npcs." + id;
        dataConfig.set(path + ".display-name", displayName);
        dataConfig.set(path + ".server", serverName);
        dataConfig.set(path + ".skin", skin);
        dataConfig.set(path + ".world", location.getWorld().getName());
        dataConfig.set(path + ".x", location.getX());
        dataConfig.set(path + ".y", location.getY());
        dataConfig.set(path + ".z", location.getZ());
        dataConfig.set(path + ".yaw", location.getYaw());
        dataConfig.set(path + ".pitch", location.getPitch());
        List<String> lines = new ArrayList<>();
        lines.add("&6&l" + displayName);
        lines.add("&7Click para jugar");
        dataConfig.set(path + ".hologram-lines", lines);
        saveData();
        spawnNPC(id);
        return true;
    }

    public boolean deleteNPC(String id) {
        if (!dataConfig.contains("npcs." + id)) return false;
        despawnNPC(id);
        dataConfig.set("npcs." + id, null);
        saveData();
        return true;
    }

    public boolean setServer(String id, String s) {
        if (!dataConfig.contains("npcs." + id)) return false;
        dataConfig.set("npcs." + id + ".server", s);
        saveData();
        return true;
    }

    public boolean setSkin(String id, String skin) {
        if (!dataConfig.contains("npcs." + id)) return false;
        dataConfig.set("npcs." + id + ".skin", skin);
        saveData();
        despawnNPC(id);
        spawnNPC(id);
        return true;
    }

    public String getServerForNPC(String npcId) {
        return dataConfig.getString("npcs." + npcId + ".server", null);
    }

    /**
     * Get NPC ID from entity ID (NMS entity ID for fake players).
     */
    public String getNPCIdFromEntityId(int entityId) {
        return entityIdMap.get(entityId);
    }

    /**
     * Get NPC ID by checking proximity to click location.
     */
    public String getNPCIdNearLocation(Location loc, double radius) {
        for (Map.Entry<String, Location> entry : npcLocations.entrySet()) {
            Location npcLoc = entry.getValue();
            if (npcLoc.getWorld().equals(loc.getWorld()) && npcLoc.distance(loc) <= radius) {
                return entry.getKey();
            }
        }
        return null;
    }

    public Set<String> getAllNPCIds() {
        ConfigurationSection s = dataConfig.getConfigurationSection("npcs");
        return s == null ? Collections.emptySet() : s.getKeys(false);
    }

    public String getNPCInfo(String id) {
        if (!dataConfig.contains("npcs." + id)) return null;
        return dataConfig.getString("npcs." + id + ".display-name", id)
                + " → " + dataConfig.getString("npcs." + id + ".server", "none")
                + " (skin: " + dataConfig.getString("npcs." + id + ".skin", "Steve") + ")";
    }

    public void handleNPCClick(Player player, String npcId) {
        String server = getServerForNPC(npcId);
        if (server == null || server.isEmpty()) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("Este NPC no tiene servidor asignado.", GRAY)));
            return;
        }
        String name = dataConfig.getString("npcs." + npcId + ".display-name", npcId);
        player.sendMessage(Component.empty()
                .append(Component.text(" ⚡ ", GOLD))
                .append(Component.text("Conectando a ", GRAY))
                .append(Component.text(name, ORANGE).decoration(TextDecoration.BOLD, true))
                .append(Component.text("...", GRAY)));
        ProxyUtils.sendToServer(plugin, player, server);
    }

    // ═══════ Spawning ═══════

    public void spawnAllNPCs() {
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            cleanOldEntities();
            for (String id : getAllNPCIds()) spawnNPC(id);
        }, 40L);
    }

    /**
     * Show all NPCs to a player who just joined.
     */
    public void showNPCsToPlayer(Player player) {
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            for (Map.Entry<String, FakePlayerNPC> entry : fakePlayerMap.entrySet()) {
                entry.getValue().showTo(player);
            }
        }, 10L);
    }

    public void despawnAllNPCs() {
        for (String id : new ArrayList<>(fakePlayerMap.keySet())) despawnNPC(id);
    }

    private void cleanOldEntities() {
        for (World w : Bukkit.getWorlds()) {
            for (Entity e : w.getEntities()) {
                if (e instanceof Villager v && !v.hasAI() && v.isInvulnerable()) v.remove();
                if (e instanceof ArmorStand a && a.isInvulnerable() && (a.isMarker() || !a.isVisible() || a.getCustomName() == null && !a.hasArms())) {
                    a.remove(); // Removes old holograms and old invisible NPC bodies
                }
            }
        }
    }

    private void spawnNPC(String id) {
        if (!dataConfig.contains("npcs." + id)) return;
        String path = "npcs." + id;
        World world = Bukkit.getWorld(dataConfig.getString(path + ".world", "world"));
        if (world == null) return;

        double x = dataConfig.getDouble(path + ".x");
        double y = dataConfig.getDouble(path + ".y");
        double z = dataConfig.getDouble(path + ".z");
        float yaw = (float) dataConfig.getDouble(path + ".yaw");
        float pitch = (float) dataConfig.getDouble(path + ".pitch");
        String skinName = dataConfig.getString(path + ".skin", "Steve");

        Location loc = new Location(world, x, y, z, yaw, pitch);

        // Create fake player NPC asynchronously (skin fetch)
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            FakePlayerNPC npc = new FakePlayerNPC(loc, skinName);

            Bukkit.getScheduler().runTask(plugin, () -> {
                fakePlayerMap.put(id, npc);
                entityIdMap.put(npc.getEntityId(), id);
                npcLocations.put(id, loc);

                // Show to all online players
                for (Player p : Bukkit.getOnlinePlayers()) {
                    if (plugin.getAuthManager().isAuthenticated(p.getUniqueId())) {
                        npc.showTo(p);
                    }
                }

                // Spawn holograms
                spawnHolograms(id, loc);
                plugin.getLogger().info("NPC real spawneado: " + id + " (skin: " + skinName + ")");
            });
        });
    }

    private void spawnHolograms(String id, Location loc) {
        List<String> lines = dataConfig.getStringList("npcs." + id + ".hologram-lines");
        if (lines == null || lines.isEmpty()) return;

        List<Entity> holos = new ArrayList<>();
        double holoY = loc.getY() + 2.3 + (lines.size() * 0.3);

        for (String line : lines) {
            holoY -= 0.3;
            ArmorStand holo = (ArmorStand) loc.getWorld().spawnEntity(
                    new Location(loc.getWorld(), loc.getX(), holoY, loc.getZ()), EntityType.ARMOR_STAND);
            holo.setInvisible(true);
            holo.setInvulnerable(true);
            holo.setGravity(false);
            holo.setSmall(true);
            holo.setMarker(true);
            holo.setCustomNameVisible(true);
            holo.setPersistent(true);
            holo.setRemoveWhenFarAway(false);
            holo.customName(net.kyori.adventure.text.serializer.legacy
                    .LegacyComponentSerializer.legacyAmpersand().deserialize(line));
            holos.add(holo);
        }
        holoMap.put(id, holos);
    }

    private void despawnNPC(String id) {
        FakePlayerNPC npc = fakePlayerMap.remove(id);
        if (npc != null) {
            entityIdMap.remove(npc.getEntityId());
            npc.destroy();
        }
        npcLocations.remove(id);

        List<Entity> holos = holoMap.remove(id);
        if (holos != null) {
            for (Entity e : holos) e.remove();
        }
    }

    private void saveData() {
        try { dataConfig.save(dataFile); }
        catch (IOException e) { e.printStackTrace(); }
    }
}
