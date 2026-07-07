package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.npc.FakePlayerNPC;
import org.bukkit.*;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.generator.ChunkGenerator;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * IslandManager - Manages player islands in a VOID world.
 * Each island is a floating platform in an entirely empty world.
 */
public class IslandManager {

    private final PrisonGens plugin;
    private File dataFile;
    private FileConfiguration dataConfig;
    private World islandWorld;

    private final Map<UUID, IslandData> islands = new ConcurrentHashMap<>();
    private final Map<String, UUID> tagIndex = new ConcurrentHashMap<>();
    // NPC entity IDs per island owner
    private final Map<UUID, FakePlayerNPC> islandNPCs = new ConcurrentHashMap<>();

    private static final int ISLAND_SPACING = 500;
    private static final int ISLAND_Y = 100;
    private static final int PLATFORM_HALF = 20;

    // ═══ Island Data ═══
    public static class IslandData {
        public UUID owner;
        public String tag;
        public int gridX, gridZ;
        public List<UUID> members = new ArrayList<>();
        public int maxMembers = 1;
        public int maxHoppers = 5;
        public int maxGens = 3;
        public int regenTicks = 600;

        public Location getCenter(World world) {
            int x = gridX * ISLAND_SPACING;
            int z = gridZ * ISLAND_SPACING;
            return new Location(world, x + 0.5, ISLAND_Y + 1, z + 0.5);
        }

        public Location getSpawn(World world) {
            Location center = getCenter(world);
            center.setYaw(180f);
            return center;
        }
    }

    // ═══ Void World Generator ═══
    public static class VoidGenerator extends ChunkGenerator {
        @Override
        public boolean shouldGenerateNoise() { return false; }
        @Override
        public boolean shouldGenerateSurface() { return false; }
        @Override
        public boolean shouldGenerateBedrock() { return false; }
        @Override
        public boolean shouldGenerateCaves() { return false; }
        @Override
        public boolean shouldGenerateDecorations() { return false; }
        @Override
        public boolean shouldGenerateMobs() { return false; }
        @Override
        public boolean shouldGenerateStructures() { return false; }
    }

    public IslandManager(PrisonGens plugin) {
        this.plugin = plugin;
        createOrLoadVoidWorld();
        loadData();
    }

    private void createOrLoadVoidWorld() {
        islandWorld = Bukkit.getWorld("prisongens_islands");
        if (islandWorld == null) {
            WorldCreator creator = new WorldCreator("prisongens_islands");
            creator.generator(new VoidGenerator());
            creator.environment(World.Environment.NORMAL);
            creator.type(WorldType.FLAT);
            creator.generateStructures(false);
            islandWorld = creator.createWorld();
            if (islandWorld != null) {
                islandWorld.setDifficulty(Difficulty.PEACEFUL);
                islandWorld.setGameRuleValue("doDaylightCycle", "false");
                islandWorld.setGameRuleValue("doWeatherCycle", "false");
                islandWorld.setGameRuleValue("doMobSpawning", "false");
                islandWorld.setGameRuleValue("keepInventory", "true");
                islandWorld.setTime(6000);
                plugin.getLogger().info("[IslandManager] Mundo void creado: prisongens_islands");
            }
        }
    }

    public World getIslandWorld() {
        return islandWorld;
    }

    // ═══ CRUD ═══

    public boolean hasIsland(Player player) {
        return islands.containsKey(player.getUniqueId());
    }

    public IslandData getIsland(Player player) {
        return islands.get(player.getUniqueId());
    }

    public IslandData getIsland(UUID uuid) {
        return islands.get(uuid);
    }

    public boolean tagExists(String tag) {
        return tagIndex.containsKey(tag.toLowerCase());
    }

    public boolean createIsland(Player player, String tag) {
        if (hasIsland(player)) return false;
        if (tagExists(tag)) return false;

        IslandData island = new IslandData();
        island.owner = player.getUniqueId();
        island.tag = tag;

        int index = islands.size();
        int gridSize = (int) Math.ceil(Math.sqrt(index + 1));
        island.gridX = index % Math.max(1, gridSize);
        island.gridZ = index / Math.max(1, gridSize);

        islands.put(player.getUniqueId(), island);
        tagIndex.put(tag.toLowerCase(), player.getUniqueId());

        generateIsland(island, player);
        saveData();

        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            player.teleport(island.getSpawn(islandWorld));
            applyWorldBorder(player, island);
        }, 20L);

        return true;
    }

    public boolean deleteIsland(Player player) {
        IslandData island = getIsland(player);
        if (island == null) return false;

        islands.remove(player.getUniqueId());
        tagIndex.remove(island.tag.toLowerCase());
        plugin.getGensManager().deleteGens(player.getUniqueId());

        // Remove NPC
        FakePlayerNPC npc = islandNPCs.remove(player.getUniqueId());
        if (npc != null) npc.destroy();

        removeWorldBorder(player);
        
        // Clear island blocks
        clearIslandArea(island);
        
        player.teleport(islandWorld.getSpawnLocation());
        saveData();
        return true;
    }

    // ═══ Generation ═══

    private void generateIsland(IslandData island, Player owner) {
        World world = islandWorld;
        Location center = island.getCenter(world);
        int cx = center.getBlockX();
        int cz = center.getBlockZ();
        int y = ISLAND_Y;

        // Main platform (circular island shape)
        for (int x = -PLATFORM_HALF; x <= PLATFORM_HALF; x++) {
            for (int z = -PLATFORM_HALF; z <= PLATFORM_HALF; z++) {
                double dist = Math.sqrt(x * x + z * z);
                if (dist > PLATFORM_HALF) continue;

                // Surface
                world.getBlockAt(cx + x, y, cz + z).setType(Material.GRASS_BLOCK);
                // Dirt layers
                world.getBlockAt(cx + x, y - 1, cz + z).setType(Material.DIRT);
                world.getBlockAt(cx + x, y - 2, cz + z).setType(Material.DIRT);
                // Stone layers with randomized depth for natural look
                int stoneDepth = 3 + (int)(Math.random() * 4);
                for (int d = 3; d < 3 + stoneDepth; d++) {
                    world.getBlockAt(cx + x, y - d, cz + z).setType(
                            Math.random() < 0.3 ? Material.COBBLESTONE : Material.STONE);
                }
            }
        }

        // Decorative paths (stone bricks from center to NPC and to mine)
        for (int z = 0; z <= 12; z++) {
            world.getBlockAt(cx, y, cz + z).setType(Material.STONE_BRICK_SLAB);
            if (z < 12) {
                world.getBlockAt(cx + 1, y, cz + z).setType(Material.STONE_BRICK_SLAB);
                world.getBlockAt(cx - 1, y, cz + z).setType(Material.STONE_BRICK_SLAB);
            }
        }
        for (int z = 0; z >= -12; z--) {
            world.getBlockAt(cx, y, cz + z).setType(Material.STONE_BRICK_SLAB);
            world.getBlockAt(cx + 1, y, cz + z).setType(Material.STONE_BRICK_SLAB);
            world.getBlockAt(cx - 1, y, cz + z).setType(Material.STONE_BRICK_SLAB);
        }

        // Spawn marker (sea lantern under glass)
        world.getBlockAt(cx, y, cz).setType(Material.SEA_LANTERN);

        // NPC platform (+10z)
        int npcZ = cz + 10;
        for (int x = -2; x <= 2; x++) {
            for (int z = -2; z <= 2; z++) {
                world.getBlockAt(cx + x, y, npcZ + z).setType(Material.POLISHED_DEEPSLATE);
            }
        }
        // NPC pillar decoration
        world.getBlockAt(cx - 2, y + 1, npcZ - 2).setType(Material.POLISHED_DEEPSLATE_WALL);
        world.getBlockAt(cx + 2, y + 1, npcZ - 2).setType(Material.POLISHED_DEEPSLATE_WALL);
        world.getBlockAt(cx - 2, y + 1, npcZ + 2).setType(Material.POLISHED_DEEPSLATE_WALL);
        world.getBlockAt(cx + 2, y + 1, npcZ + 2).setType(Material.POLISHED_DEEPSLATE_WALL);
        world.getBlockAt(cx - 2, y + 2, npcZ - 2).setType(Material.LANTERN);
        world.getBlockAt(cx + 2, y + 2, npcZ - 2).setType(Material.LANTERN);
        world.getBlockAt(cx - 2, y + 2, npcZ + 2).setType(Material.LANTERN);
        world.getBlockAt(cx + 2, y + 2, npcZ + 2).setType(Material.LANTERN);

        // Spawn NPC with player's skin
        Location npcLoc = new Location(world, cx + 0.5, y + 1, npcZ + 0.5);
        npcLoc.setYaw(180f);
        spawnGensNPC(island, npcLoc, owner.getName());

        // Mine area (south of spawn, -10z offset) - initially empty, will be filled by gens
        buildMineShell(island, 5); // Default minimum mine size
    }

    /**
     * Build or rebuild the bedrock mine shell based on radius.
     */
    public void buildMineShell(IslandData island, int radius) {
        World world = islandWorld;
        Location center = island.getCenter(world);
        int cx = center.getBlockX();
        int cz = center.getBlockZ() - 10; // South offset
        int y = ISLAND_Y;
        int depth = 15;

        // Clear old mine area (max possible)
        for (int x = -18; x <= 18; x++) {
            for (int z = -18; z <= 18; z++) {
                for (int d = -depth - 1; d <= 2; d++) {
                    Material mat = world.getBlockAt(cx + x, y + d, cz + z).getType();
                    if (mat == Material.BEDROCK || mat == Material.OAK_FENCE) {
                        world.getBlockAt(cx + x, y + d, cz + z).setType(Material.AIR);
                    }
                }
            }
        }

        int r = Math.max(3, Math.min(radius, 16));

        // Build bedrock walls
        for (int x = -(r + 1); x <= (r + 1); x++) {
            for (int z = -(r + 1); z <= (r + 1); z++) {
                boolean isWall = Math.abs(x) == r + 1 || Math.abs(z) == r + 1;

                if (isWall) {
                    for (int d = 0; d <= depth; d++) {
                        world.getBlockAt(cx + x, y - d, cz + z).setType(Material.BEDROCK);
                    }
                    world.getBlockAt(cx + x, y + 1, cz + z).setType(Material.OAK_FENCE);
                } else {
                    for (int d = 0; d < depth; d++) {
                        world.getBlockAt(cx + x, y - d, cz + z).setType(Material.AIR);
                    }
                    world.getBlockAt(cx + x, y - depth, cz + z).setType(Material.BEDROCK);
                }
            }
        }
    }

    /**
     * Get the mine center location for an island.
     */
    public Location getMineCenter(IslandData island) {
        Location center = island.getCenter(islandWorld);
        return new Location(islandWorld, center.getBlockX(), ISLAND_Y, center.getBlockZ() - 10);
    }

    private void clearIslandArea(IslandData island) {
        World world = islandWorld;
        Location center = island.getCenter(world);
        int cx = center.getBlockX();
        int cz = center.getBlockZ();
        int y = ISLAND_Y;

        for (int x = -(PLATFORM_HALF + 20); x <= (PLATFORM_HALF + 20); x++) {
            for (int z = -(PLATFORM_HALF + 20); z <= (PLATFORM_HALF + 20); z++) {
                for (int d = -20; d <= 5; d++) {
                    world.getBlockAt(cx + x, y + d, cz + z).setType(Material.AIR);
                }
            }
        }
    }

    // ═══ NPC ═══

    public void spawnGensNPC(IslandData island, Location loc, String skinName) {
        try {
            FakePlayerNPC npc = new FakePlayerNPC(loc, skinName, plugin);
            islandNPCs.put(island.owner, npc);

            // Show to all online players
            for (Player p : Bukkit.getOnlinePlayers()) {
                npc.showTo(p);
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Error spawning NPC: " + e.getMessage());
            e.printStackTrace();
        }
    }

    public void showNPCsTo(Player player) {
        for (FakePlayerNPC npc : islandNPCs.values()) {
            npc.showTo(player);
        }
    }

    public FakePlayerNPC getNPC(UUID owner) {
        return islandNPCs.get(owner);
    }

    public Map<UUID, FakePlayerNPC> getAllNPCs() {
        return islandNPCs;
    }

    // ═══ World Border ═══

    public void applyWorldBorder(Player player, IslandData island) {
        org.bukkit.WorldBorder border = Bukkit.createWorldBorder();
        Location center = island.getCenter(islandWorld);
        border.setCenter(center);

        // Calculate border size based on gens mine size
        int mineRadius = plugin.getGensManager().calculateMineRadius(player.getUniqueId());
        int borderSize = Math.max(50, (PLATFORM_HALF + mineRadius + 5) * 2);
        border.setSize(borderSize);
        border.setWarningDistance(0);
        border.setDamageAmount(0);
        player.setWorldBorder(border);
    }

    public void removeWorldBorder(Player player) {
        player.setWorldBorder(null);
    }

    // ═══ Upgrades ═══

    public int getMemberUpgradeCost(IslandData island) { return island.maxMembers * 5000; }
    public int getHopperUpgradeCost(IslandData island) { return island.maxHoppers * 3000; }
    public int getGenCapacityUpgradeCost(IslandData island) { return island.maxGens * 10000; }
    public int getRegenUpgradeCost(IslandData island) { return (600 - island.regenTicks + 100) * 50; }

    public boolean upgradeMemberSlots(Player player) {
        IslandData island = getIsland(player);
        if (island == null) return false;
        if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.MONEY, getMemberUpgradeCost(island))) return false;
        island.maxMembers++;
        saveData();
        return true;
    }

    public boolean upgradeHopperLimit(Player player) {
        IslandData island = getIsland(player);
        if (island == null) return false;
        if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.MONEY, getHopperUpgradeCost(island))) return false;
        island.maxHoppers += 5;
        saveData();
        return true;
    }

    public boolean upgradeGenCapacity(Player player) {
        IslandData island = getIsland(player);
        if (island == null) return false;
        if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.MONEY, getGenCapacityUpgradeCost(island))) return false;
        island.maxGens++;
        saveData();
        return true;
    }

    public boolean upgradeRegenSpeed(Player player) {
        IslandData island = getIsland(player);
        if (island == null) return false;
        if (island.regenTicks <= 100) return false;
        if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.TOKENS, getRegenUpgradeCost(island))) return false;
        island.regenTicks -= 100;
        saveData();
        return true;
    }

    // ═══ Persistence ═══

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "islands.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        if (dataConfig.contains("islands")) {
            var section = dataConfig.getConfigurationSection("islands");
            if (section != null) {
                for (String uuidStr : section.getKeys(false)) {
                    UUID uuid = UUID.fromString(uuidStr);
                    IslandData island = new IslandData();
                    island.owner = uuid;
                    island.tag = section.getString(uuidStr + ".tag", "island");
                    island.gridX = section.getInt(uuidStr + ".gridX", 0);
                    island.gridZ = section.getInt(uuidStr + ".gridZ", 0);
                    island.maxMembers = section.getInt(uuidStr + ".maxMembers", 1);
                    island.maxHoppers = section.getInt(uuidStr + ".maxHoppers", 5);
                    island.maxGens = section.getInt(uuidStr + ".maxGens", 3);
                    island.regenTicks = section.getInt(uuidStr + ".regenTicks", 600);

                    List<String> memberStrs = section.getStringList(uuidStr + ".members");
                    for (String m : memberStrs) {
                        try { island.members.add(UUID.fromString(m)); } catch (Exception ignored) {}
                    }

                    islands.put(uuid, island);
                    tagIndex.put(island.tag.toLowerCase(), uuid);
                }
            }
        }
    }

    public void saveData() {
        dataConfig.set("islands", null);
        for (Map.Entry<UUID, IslandData> entry : islands.entrySet()) {
            String path = "islands." + entry.getKey().toString();
            IslandData island = entry.getValue();
            dataConfig.set(path + ".tag", island.tag);
            dataConfig.set(path + ".gridX", island.gridX);
            dataConfig.set(path + ".gridZ", island.gridZ);
            dataConfig.set(path + ".maxMembers", island.maxMembers);
            dataConfig.set(path + ".maxHoppers", island.maxHoppers);
            dataConfig.set(path + ".maxGens", island.maxGens);
            dataConfig.set(path + ".regenTicks", island.regenTicks);

            List<String> memberStrs = new ArrayList<>();
            for (UUID m : island.members) memberStrs.add(m.toString());
            dataConfig.set(path + ".members", memberStrs);
        }
        try { dataConfig.save(dataFile); } catch (IOException e) { e.printStackTrace(); }
    }
}
