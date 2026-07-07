package com.servermc.prisongens.mine;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.gen.GenCategory;
import com.servermc.prisongens.managers.IslandManager;
import org.bukkit.*;
import org.bukkit.block.data.BlockData;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.scheduler.BukkitTask;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * MineManager - Minas dinámicas por isla.
 * Una isla tiene N slots de GEN. El GEN primario (slot 0) define la
 * composición base; los demás aportan puntos de tamaño y mezcla ponderada.
 * El tamaño está acotado por: etapa máxima de la categoría primaria,
 * capacidad de alimentación total y espacio físico de la isla.
 * Los resets y crecimientos son batched (N bloques/tick) para evitar lag.
 */
public class MineManager {

    public static class Stage {
        public final int half, depth, points;
        public Stage(int half, int depth, int points) { this.half = half; this.depth = depth; this.points = points; }
        public int width() { return half * 2 + 1; }
    }

    public static class MineData {
        public UUID owner;
        public ItemStack[] genSlots = new ItemStack[0];
        public int currentStage = 0; // índice de etapa; -1 sin mina
        public int resetCountdown = 0;

        public boolean hasActiveGen() {
            for (ItemStack it : genSlots) if (it != null) return true;
            return false;
        }
    }

    /** Trabajo de colocación batched. */
    private static class PlacementJob {
        final UUID owner;
        final Deque<long[]> blocks; // {x, y, z, materialOrdinal}
        final boolean announce;
        PlacementJob(UUID owner, Deque<long[]> blocks, boolean announce) {
            this.owner = owner; this.blocks = blocks; this.announce = announce;
        }
    }

    private final PrisonGens plugin;
    private final Map<UUID, MineData> mines = new ConcurrentHashMap<>();
    private final Queue<PlacementJob> jobQueue = new ConcurrentLinkedQueue<>();
    private final Set<UUID> queuedOwners = ConcurrentHashMap.newKeySet();
    private final List<Stage> stages = new ArrayList<>();
    private final Map<GenCategory, List<Map.Entry<Material, Integer>>> compositions = new EnumMap<>(GenCategory.class);
    private final Map<Material, Double> prices = new EnumMap<>(Material.class);
    private final Random rng = new Random();

    private File dataFile;
    private BukkitTask placementTask;
    private BukkitTask resetTask;

    private int blocksPerTick = 2500;
    private int defaultResetTicks = 1200;
    private int minResetTicks = 200;
    private int capacityPerStage = 8;

    public static final int MINE_OFFSET_Z = -45;

    public MineManager(PrisonGens plugin) {
        this.plugin = plugin;
        loadConfig();
        loadData();
    }

    // ═══ Configuración ═══

    public void loadConfig() {
        FileConfiguration cfg = plugin.getMinesConfig();
        blocksPerTick = cfg.getInt("blocks-per-tick", 2500);
        defaultResetTicks = cfg.getInt("default-reset-ticks", 1200);
        minResetTicks = cfg.getInt("min-reset-ticks", 200);
        capacityPerStage = cfg.getInt("capacity-per-stage", 8);

        stages.clear();
        List<Map<?, ?>> stageList = cfg.getMapList("stages");
        for (Map<?, ?> m : stageList) {
            int half = ((Number) m.getOrDefault("half", 2)).intValue();
            int depth = ((Number) m.getOrDefault("depth", 10)).intValue();
            int points = ((Number) m.getOrDefault("points", 0)).intValue();
            stages.add(new Stage(half, depth, points));
        }
        if (stages.isEmpty()) {
            stages.add(new Stage(2, 10, 0));
            stages.add(new Stage(3, 11, 3));
            stages.add(new Stage(4, 12, 7));
            stages.add(new Stage(5, 12, 12));
            stages.add(new Stage(7, 13, 20));
            stages.add(new Stage(9, 14, 32));
            stages.add(new Stage(12, 15, 50));
            stages.add(new Stage(15, 16, 75));
        }

        compositions.clear();
        ConfigurationSection compSec = cfg.getConfigurationSection("composition");
        for (GenCategory cat : GenCategory.values()) {
            List<Map.Entry<Material, Integer>> list = new ArrayList<>();
            ConfigurationSection sec = compSec != null ? compSec.getConfigurationSection(cat.name()) : null;
            if (sec != null) {
                for (String key : sec.getKeys(false)) {
                    try {
                        list.add(Map.entry(Material.valueOf(key.toUpperCase()), sec.getInt(key)));
                    } catch (IllegalArgumentException ignored) {}
                }
            }
            if (list.isEmpty()) list.add(Map.entry(Material.COBBLESTONE, 100));
            compositions.put(cat, list);
        }

        prices.clear();
        ConfigurationSection priceSec = cfg.getConfigurationSection("prices");
        if (priceSec != null) {
            for (String key : priceSec.getKeys(false)) {
                try {
                    prices.put(Material.valueOf(key.toUpperCase()), priceSec.getDouble(key));
                } catch (IllegalArgumentException ignored) {}
            }
        }
    }

    public double getBlockPrice(Material mat) { return prices.getOrDefault(mat, 0.5); }
    public List<Stage> getStages() { return stages; }
    public int getDefaultResetTicks() { return defaultResetTicks; }
    public int getMinResetTicks() { return minResetTicks; }

    // ═══ Acceso a datos ═══

    public MineData getMine(UUID owner) {
        return mines.computeIfAbsent(owner, k -> {
            MineData d = new MineData();
            d.owner = k;
            d.resetCountdown = defaultResetTicks;
            return d;
        });
    }

    public void deleteMine(UUID owner) {
        mines.remove(owner);
        queuedOwners.remove(owner);
        saveData();
    }

    /** Asegura que el array de slots coincida con maxGens de la isla. */
    public void ensureSlots(UUID owner) {
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(owner);
        if (island == null) return;
        MineData mine = getMine(owner);
        if (mine.genSlots.length != island.maxGens) {
            mine.genSlots = Arrays.copyOf(mine.genSlots, island.maxGens);
        }
    }

    public ItemStack getPrimaryGen(UUID owner) {
        MineData mine = getMine(owner);
        for (ItemStack it : mine.genSlots) if (it != null) return it;
        return null;
    }

    // ═══ Inserción / retiro de GENS ═══

    /** Inserta un GEN en el primer slot libre. Devuelve slot o -1. */
    public int insertGen(UUID owner, ItemStack gen) {
        ensureSlots(owner);
        MineData mine = getMine(owner);
        for (int i = 0; i < mine.genSlots.length; i++) {
            if (mine.genSlots[i] == null) {
                ItemStack single = gen.clone();
                single.setAmount(1);
                mine.genSlots[i] = single;
                onGensChanged(owner);
                saveData();
                return i;
            }
        }
        return -1;
    }

    /** Retira el GEN del slot indicado. Devuelve el ítem con todo su estado. */
    public ItemStack withdrawGen(UUID owner, int slot) {
        MineData mine = getMine(owner);
        if (slot < 0 || slot >= mine.genSlots.length) return null;
        ItemStack item = mine.genSlots[slot];
        mine.genSlots[slot] = null;
        if (item != null) {
            onGensChanged(owner);
            saveData();
        }
        return item;
    }

    /** Llamar cuando cambian los GENS activos: recalcula etapa y reconstruye si cambió. */
    public void onGensChanged(UUID owner) {
        MineData mine = getMine(owner);
        int newStage = computeStage(owner);
        if (!mine.hasActiveGen()) {
            // Vaciar la mina físicamente
            clearMine(owner);
            mine.currentStage = 0;
        } else if (newStage != mine.currentStage) {
            mine.currentStage = newStage;
            rebuildMine(owner, true);
        } else {
            resetMine(owner, false);
        }
        plugin.getHologramManager().updateMineHologram(owner);
    }

    // ═══ Cálculo de etapa ═══

    /** Puntos de tamaño = suma de niveles de todos los GENS activos. */
    public int computeSizePoints(UUID owner) {
        MineData mine = getMine(owner);
        int points = 0;
        for (ItemStack it : mine.genSlots) {
            if (it != null) points += plugin.getGenItemFactory().getLevel(it);
        }
        return points;
    }

    public int computeStage(UUID owner) {
        MineData mine = getMine(owner);
        if (!mine.hasActiveGen()) return 0;

        int points = computeSizePoints(owner);

        // Etapa por puntos
        int byPoints = 0;
        for (int i = 0; i < stages.size(); i++) {
            if (points >= stages.get(i).points) byPoints = i;
        }

        // Tope por categoría del GEN primario
        ItemStack primary = getPrimaryGen(owner);
        GenCategory cat = plugin.getGenItemFactory().getCategory(primary);
        int byCategory = cat != null ? Math.min(stages.size() - 1, cat.maxStage - 1) : 0;

        // Tope por capacidad de alimentación total (base + bonus + mejora de isla)
        int totalCap = 0;
        for (ItemStack it : getMine(owner).genSlots) {
            if (it != null) totalCap += plugin.getGenItemFactory().getCapacity(it);
        }
        totalCap += plugin.getUpgradeManager().getFeedCapacityBonus(owner);
        int byCapacity = Math.min(stages.size() - 1, totalCap / Math.max(1, capacityPerStage));

        // Tope por espacio físico de la isla
        int islandSize = plugin.getUpgradeManager().getIslandSize(owner);
        int byIsland = 0;
        for (int i = 0; i < stages.size(); i++) {
            if (stages.get(i).width() + 6 <= islandSize) byIsland = i;
        }

        return Math.max(0, Math.min(Math.min(byPoints, byCategory), Math.min(byCapacity, byIsland)));
    }

    /** ¿El crecimiento está bloqueado por espacio de isla? */
    public boolean isBlockedByIslandSize(UUID owner) {
        MineData mine = getMine(owner);
        if (!mine.hasActiveGen()) return false;
        int points = computeSizePoints(owner);
        int byPoints = 0;
        for (int i = 0; i < stages.size(); i++) {
            if (points >= stages.get(i).points) byPoints = i;
        }
        int islandSize = plugin.getUpgradeManager().getIslandSize(owner);
        int byIsland = 0;
        for (int i = 0; i < stages.size(); i++) {
            if (stages.get(i).width() + 6 <= islandSize) byIsland = i;
        }
        return byPoints > byIsland && computeStage(owner) == byIsland;
    }

    // ═══ Región ═══

    public Location getMineCenter(UUID owner) {
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(owner);
        if (island == null) return null;
        World world = plugin.getIslandManager().getIslandWorld();
        Location c = island.getCenter(world);
        return new Location(world, c.getBlockX(), IslandManager.ISLAND_Y, c.getBlockZ() + MINE_OFFSET_Z);
    }

    public Stage getCurrentStage(UUID owner) {
        MineData mine = getMine(owner);
        int idx = Math.max(0, Math.min(mine.currentStage, stages.size() - 1));
        return stages.get(idx);
    }

    public int getMineDepth(UUID owner) {
        return getCurrentStage(owner).depth + plugin.getUpgradeManager().getMineHeightBonus(owner);
    }

    /** ¿La ubicación está dentro de la zona minable de la mina de owner? */
    public boolean isInsideMine(UUID owner, Location loc) {
        MineData mine = getMine(owner);
        if (!mine.hasActiveGen()) return false;
        Location center = getMineCenter(owner);
        if (center == null || loc.getWorld() != center.getWorld()) return false;
        Stage stage = getCurrentStage(owner);
        int depth = getMineDepth(owner);
        int dx = loc.getBlockX() - center.getBlockX();
        int dz = loc.getBlockZ() - center.getBlockZ();
        int dy = center.getBlockY() - loc.getBlockY();
        return Math.abs(dx) <= stage.half && Math.abs(dz) <= stage.half && dy >= 1 && dy <= depth;
    }

    /** Busca al dueño de la mina que contiene esta ubicación (o null). */
    public UUID findMineOwnerAt(Location loc) {
        for (UUID owner : mines.keySet()) {
            if (isInsideMine(owner, loc)) return owner;
        }
        return null;
    }

    // ═══ Composición ═══

    /** Paleta ponderada mezclando la composición de todos los GENS activos. */
    private List<Map.Entry<Material, Integer>> buildPalette(UUID owner) {
        MineData mine = getMine(owner);
        Map<Material, Integer> merged = new EnumMap<>(Material.class);
        boolean first = true;
        for (ItemStack it : mine.genSlots) {
            if (it == null) continue;
            GenCategory cat = plugin.getGenItemFactory().getCategory(it);
            if (cat == null) continue;
            // El primario pesa x3, los secundarios x1
            int weight = first ? 3 : 1;
            first = false;
            for (Map.Entry<Material, Integer> e : compositions.get(cat)) {
                merged.merge(e.getKey(), e.getValue() * weight, Integer::sum);
            }
        }
        if (merged.isEmpty()) merged.put(Material.COBBLESTONE, 100);
        return new ArrayList<>(merged.entrySet());
    }

    private Material pickMaterial(List<Map.Entry<Material, Integer>> palette, int totalWeight) {
        int r = rng.nextInt(totalWeight);
        int acc = 0;
        for (Map.Entry<Material, Integer> e : palette) {
            acc += e.getValue();
            if (r < acc) return e.getKey();
        }
        return palette.get(0).getKey();
    }

    // ═══ Construcción / reset batched ═══

    /** Reconstruye toda la mina (shell + contenido). Usado en crecimiento. */
    public void rebuildMine(UUID owner, boolean announce) {
        Location center = getMineCenter(owner);
        if (center == null) return;
        MineData mine = getMine(owner);
        if (!mine.hasActiveGen()) return;

        Stage stage = getCurrentStage(owner);
        int depth = getMineDepth(owner);
        int cx = center.getBlockX(), cy = center.getBlockY(), cz = center.getBlockZ();

        Deque<long[]> blocks = new ArrayDeque<>();

        // 1. Limpiar zona máxima posible (paredes viejas)
        int maxHalf = stages.get(stages.size() - 1).half + 1;
        int maxDepth = stages.get(stages.size() - 1).depth + 12;
        for (int x = -maxHalf; x <= maxHalf; x++) {
            for (int z = -maxHalf; z <= maxHalf; z++) {
                for (int y = 1; y >= -maxDepth; y--) {
                    blocks.add(new long[]{cx + x, cy + y, cz + z, Material.AIR.ordinal()});
                }
            }
        }

        // 2. Paredes de bedrock + borde superior
        int r = stage.half + 1;
        for (int x = -r; x <= r; x++) {
            for (int z = -r; z <= r; z++) {
                boolean isWall = Math.abs(x) == r || Math.abs(z) == r;
                if (isWall) {
                    for (int y = 0; y >= -depth; y--) {
                        blocks.add(new long[]{cx + x, cy + y, cz + z, Material.BEDROCK.ordinal()});
                    }
                    blocks.add(new long[]{cx + x, cy + 1, cz + z, Material.OAK_FENCE.ordinal()});
                } else {
                    blocks.add(new long[]{cx + x, cy - depth - 1, cz + z, Material.BEDROCK.ordinal()});
                }
            }
        }

        // 3. Contenido
        appendFill(blocks, owner, stage, depth, cx, cy, cz);

        enqueue(owner, blocks, announce);
    }

    /** Rellena solo el interior (reset normal, sin reconstruir paredes). */
    public void resetMine(UUID owner, boolean announce) {
        Location center = getMineCenter(owner);
        if (center == null) return;
        MineData mine = getMine(owner);
        if (!mine.hasActiveGen()) return;
        if (queuedOwners.contains(owner)) return; // ya hay un trabajo en cola

        Stage stage = getCurrentStage(owner);
        int depth = getMineDepth(owner);
        Deque<long[]> blocks = new ArrayDeque<>();
        appendFill(blocks, owner, stage, depth, center.getBlockX(), center.getBlockY(), center.getBlockZ());
        enqueue(owner, blocks, announce);
    }

    private void appendFill(Deque<long[]> blocks, UUID owner, Stage stage, int depth, int cx, int cy, int cz) {
        List<Map.Entry<Material, Integer>> palette = buildPalette(owner);
        int totalWeight = palette.stream().mapToInt(Map.Entry::getValue).sum();
        for (int x = -stage.half; x <= stage.half; x++) {
            for (int z = -stage.half; z <= stage.half; z++) {
                for (int y = 1; y <= depth; y++) {
                    Material mat = pickMaterial(palette, totalWeight);
                    blocks.add(new long[]{cx + x, cy - y, cz + z, mat.ordinal()});
                }
            }
        }
    }

    /** Vacía físicamente la mina (cuando se retiran todos los GENS). */
    public void clearMine(UUID owner) {
        Location center = getMineCenter(owner);
        if (center == null) return;
        int cx = center.getBlockX(), cy = center.getBlockY(), cz = center.getBlockZ();
        int maxHalf = stages.get(stages.size() - 1).half + 1;
        int maxDepth = stages.get(stages.size() - 1).depth + 12;
        Deque<long[]> blocks = new ArrayDeque<>();
        for (int x = -maxHalf; x <= maxHalf; x++) {
            for (int z = -maxHalf; z <= maxHalf; z++) {
                for (int y = 1; y >= -maxDepth; y--) {
                    blocks.add(new long[]{cx + x, cy + y, cz + z, Material.AIR.ordinal()});
                }
            }
        }
        enqueue(owner, blocks, false);
    }

    private void enqueue(UUID owner, Deque<long[]> blocks, boolean announce) {
        // Subir a jugadores dentro de la mina antes de colocar
        teleportPlayersOut(owner);
        queuedOwners.add(owner);
        jobQueue.add(new PlacementJob(owner, blocks, announce));
    }

    private void teleportPlayersOut(UUID owner) {
        Location center = getMineCenter(owner);
        if (center == null) return;
        Stage stage = getCurrentStage(owner);
        for (Player p : Bukkit.getOnlinePlayers()) {
            if (p.getWorld() != center.getWorld()) continue;
            int dx = p.getLocation().getBlockX() - center.getBlockX();
            int dz = p.getLocation().getBlockZ() - center.getBlockZ();
            if (Math.abs(dx) <= stage.half + 1 && Math.abs(dz) <= stage.half + 1
                    && p.getLocation().getBlockY() <= center.getBlockY() + 1) {
                Location safe = center.clone().add(0.5, 2, stage.half + 3.5);
                p.teleport(safe);
                p.playSound(p.getLocation(), Sound.ENTITY_ENDERMAN_TELEPORT, 0.7f, 1.2f);
            }
        }
    }

    // ═══ Tasks ═══

    public void startTasks() {
        // Task de colocación batched: N bloques por tick, física desactivada
        Material[] materials = Material.values();
        placementTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            int budget = blocksPerTick;
            World world = plugin.getIslandManager().getIslandWorld();
            if (world == null) return;
            while (budget > 0) {
                PlacementJob job = jobQueue.peek();
                if (job == null) return;
                while (budget > 0 && !job.blocks.isEmpty()) {
                    long[] b = job.blocks.poll();
                    BlockData data = materials[(int) b[3]].createBlockData();
                    world.getBlockAt((int) b[0], (int) b[1], (int) b[2]).setBlockData(data, false);
                    budget--;
                }
                if (job.blocks.isEmpty()) {
                    jobQueue.poll();
                    queuedOwners.remove(job.owner);
                    onJobComplete(job);
                }
            }
        }, 1L, 1L);

        // Task de reset automático (chequeo cada segundo)
        resetTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            for (MineData mine : mines.values()) {
                if (!mine.hasActiveGen()) continue;
                Player owner = Bukkit.getPlayer(mine.owner);
                if (owner == null || !owner.isOnline()) continue;
                mine.resetCountdown -= 20;
                if (mine.resetCountdown <= 0) {
                    mine.resetCountdown = getResetTicks(mine.owner);
                    resetMine(mine.owner, false);
                }
            }
        }, 20L, 20L);
    }

    public int getResetTicks(UUID owner) {
        int reduction = plugin.getUpgradeManager().getResetReductionTicks(owner);
        return Math.max(minResetTicks, defaultResetTicks - reduction);
    }

    private void onJobComplete(PlacementJob job) {
        Location center = getMineCenter(job.owner);
        if (center == null) return;
        World world = center.getWorld();
        Stage stage = getCurrentStage(job.owner);
        Location fx = center.clone().add(0.5, 1.5, 0.5);
        world.spawnParticle(Particle.HAPPY_VILLAGER, fx, 40, stage.half, 1.5, stage.half, 0);
        Player owner = Bukkit.getPlayer(job.owner);
        if (owner != null && owner.isOnline()) {
            if (job.announce) {
                owner.sendMessage("§a§l✓ §7¡Tu mina creció a §f" + stage.width() + "x" + stage.width() + "§7!");
                owner.playSound(owner.getLocation(), Sound.ENTITY_PLAYER_LEVELUP, 1f, 1.0f);
                world.spawnParticle(Particle.FIREWORK, fx, 80, stage.half, 2, stage.half, 0.05);
            } else if (owner.getWorld() == world
                    && owner.getLocation().distanceSquared(center) < 60 * 60) {
                owner.playSound(owner.getLocation(), Sound.BLOCK_AMETHYST_BLOCK_CHIME, 0.6f, 1.4f);
            }
        }
        plugin.getHologramManager().updateMineHologram(job.owner);
    }

    public void stopTasks() {
        if (placementTask != null) placementTask.cancel();
        if (resetTask != null) resetTask.cancel();
        // Vaciar la cola inmediatamente al apagar
        World world = plugin.getIslandManager().getIslandWorld();
        Material[] materials = Material.values();
        PlacementJob job;
        while ((job = jobQueue.poll()) != null) {
            if (world == null) continue;
            while (!job.blocks.isEmpty()) {
                long[] b = job.blocks.poll();
                world.getBlockAt((int) b[0], (int) b[1], (int) b[2])
                        .setBlockData(materials[(int) b[3]].createBlockData(), false);
            }
        }
        queuedOwners.clear();
    }

    // ═══ Persistencia ═══

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "minedata.yml");
        if (!dataFile.exists()) return;
        FileConfiguration cfg = YamlConfiguration.loadConfiguration(dataFile);
        ConfigurationSection sec = cfg.getConfigurationSection("mines");
        if (sec == null) return;
        for (String uuidStr : sec.getKeys(false)) {
            try {
                UUID owner = UUID.fromString(uuidStr);
                MineData mine = new MineData();
                mine.owner = owner;
                mine.currentStage = sec.getInt(uuidStr + ".stage", 0);
                mine.resetCountdown = defaultResetTicks;
                ConfigurationSection slots = sec.getConfigurationSection(uuidStr + ".slots");
                int maxSlot = 0;
                if (slots != null) {
                    for (String s : slots.getKeys(false)) maxSlot = Math.max(maxSlot, Integer.parseInt(s));
                }
                mine.genSlots = new ItemStack[Math.max(3, maxSlot + 1)];
                if (slots != null) {
                    for (String s : slots.getKeys(false)) {
                        mine.genSlots[Integer.parseInt(s)] = slots.getItemStack(s);
                    }
                }
                mines.put(owner, mine);
            } catch (Exception e) {
                plugin.getLogger().warning("[MineManager] Error cargando mina " + uuidStr + ": " + e.getMessage());
            }
        }
    }

    public void saveData() {
        YamlConfiguration cfg = new YamlConfiguration();
        for (Map.Entry<UUID, MineData> entry : mines.entrySet()) {
            MineData mine = entry.getValue();
            String path = "mines." + entry.getKey();
            cfg.set(path + ".stage", mine.currentStage);
            for (int i = 0; i < mine.genSlots.length; i++) {
                if (mine.genSlots[i] != null) {
                    cfg.set(path + ".slots." + i, mine.genSlots[i]);
                }
            }
        }
        try { cfg.save(dataFile); } catch (IOException e) { e.printStackTrace(); }
    }

    public Map<UUID, MineData> getAllMines() { return mines; }
}
