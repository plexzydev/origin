package com.servermc.prisongens.robot;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.EconomyManager;
import com.servermc.prisongens.mine.MineManager;
import org.bukkit.*;
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

/**
 * RobotManager - Robots por isla. Cada robot es un ItemStack almacenado
 * en un slot; genera ingresos pasivos por segundo mientras el dueño está
 * conectado (u offline si se habilita en robots.yml). Trabajan sobre la
 * mina del GEN activo: a mayor etapa de mina, mejores robots permitidos.
 */
public class RobotManager {

    private final PrisonGens plugin;
    private final Map<UUID, ItemStack[]> robotSlots = new ConcurrentHashMap<>();
    private final Map<Integer, Integer> stageRequirement = new HashMap<>();
    private final Random rng = new Random();

    private File dataFile;
    private BukkitTask incomeTask;

    private boolean offlineEarnings = false;
    private double incomeMultiplier = 1.0;
    private boolean visualMining = true;

    public RobotManager(PrisonGens plugin) {
        this.plugin = plugin;
        loadConfig();
        loadData();
    }

    public void loadConfig() {
        FileConfiguration cfg = plugin.getRobotsConfig();
        offlineEarnings = cfg.getBoolean("offline-earnings", false);
        incomeMultiplier = cfg.getDouble("income-multiplier", 1.0);
        visualMining = cfg.getBoolean("visual-mining", true);

        stageRequirement.clear();
        ConfigurationSection sec = cfg.getConfigurationSection("mine-stage-requirement");
        if (sec != null) {
            for (String key : sec.getKeys(false)) {
                try { stageRequirement.put(Integer.parseInt(key), sec.getInt(key)); }
                catch (NumberFormatException ignored) {}
            }
        }
    }

    public double getIncomeMultiplier() { return incomeMultiplier; }

    // ═══ Slots ═══

    /** Slots disponibles según la mejora ROBOT_SLOTS de la isla. */
    public int getMaxSlots(UUID owner) {
        return plugin.getUpgradeManager().getRobotSlots(owner);
    }

    public ItemStack[] getSlots(UUID owner) {
        int max = Math.max(1, getMaxSlots(owner));
        ItemStack[] slots = robotSlots.computeIfAbsent(owner, k -> new ItemStack[max]);
        if (slots.length != max) {
            slots = Arrays.copyOf(slots, max);
            robotSlots.put(owner, slots);
        }
        return slots;
    }

    public int countActive(UUID owner) {
        int n = 0;
        for (ItemStack it : getSlots(owner)) if (it != null) n++;
        return n;
    }

    /** Etapa de mina requerida para un robot de este tier. */
    public int requiredStage(RobotCategory cat) {
        return stageRequirement.getOrDefault(cat.tier, 0);
    }

    /** ¿La mina actual permite este robot? */
    public boolean canUseRobot(UUID owner, ItemStack robot) {
        RobotCategory cat = plugin.getRobotItemFactory().getCategory(robot);
        if (cat == null) return false;
        MineManager.MineData mine = plugin.getMineManager().getMine(owner);
        if (!mine.hasActiveGen()) return false;
        return mine.currentStage >= requiredStage(cat);
    }

    /** Inserta un robot en el primer slot libre. Devuelve slot o -1. */
    public int insertRobot(UUID owner, ItemStack robot) {
        ItemStack[] slots = getSlots(owner);
        for (int i = 0; i < slots.length; i++) {
            if (slots[i] == null) {
                ItemStack single = robot.clone();
                single.setAmount(1);
                slots[i] = single;
                saveData();
                return i;
            }
        }
        return -1;
    }

    /** Retira el robot del slot indicado con todo su estado. */
    public ItemStack withdrawRobot(UUID owner, int slot) {
        ItemStack[] slots = getSlots(owner);
        if (slot < 0 || slot >= slots.length) return null;
        ItemStack item = slots[slot];
        slots[slot] = null;
        if (item != null) saveData();
        return item;
    }

    public void deleteRobots(UUID owner) {
        robotSlots.remove(owner);
        saveData();
    }

    // ═══ Ingresos pasivos ═══

    public void startIncomeTask() {
        incomeTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            for (Map.Entry<UUID, ItemStack[]> entry : robotSlots.entrySet()) {
                UUID owner = entry.getKey();
                Player p = Bukkit.getPlayer(owner);
                boolean online = p != null && p.isOnline();
                if (!online && !offlineEarnings) continue;

                MineManager.MineData mine = plugin.getMineManager().getMine(owner);
                if (!mine.hasActiveGen()) continue;

                double money = 0;
                int tokens = 0;
                int robots = 0;
                for (ItemStack robot : entry.getValue()) {
                    if (robot == null) continue;
                    RobotCategory cat = plugin.getRobotItemFactory().getCategory(robot);
                    if (cat == null) continue;
                    // Si la mina bajó de etapa, robots de tier alto se pausan
                    if (mine.currentStage < requiredStage(cat)) continue;
                    int level = plugin.getRobotItemFactory().getLevel(robot);
                    money += cat.moneyPerSec * level * incomeMultiplier;
                    double chance = Math.min(0.9, cat.tokenChance * level);
                    if (rng.nextDouble() < chance) tokens += 1 + rng.nextInt(cat.tier);
                    robots++;
                }
                if (robots == 0) continue;

                if (money > 0) plugin.getEconomyManager().addBalance(owner, EconomyManager.MONEY, money);
                if (tokens > 0) plugin.getEconomyManager().addBalance(owner, EconomyManager.TOKENS, tokens);

                // Efecto visual: los robots "trabajan" en la mina
                if (online && visualMining) {
                    Location center = plugin.getMineManager().getMineCenter(owner);
                    if (center != null && p.getWorld() == center.getWorld()
                            && p.getLocation().distanceSquared(center) < 70 * 70) {
                        MineManager.Stage stage = plugin.getMineManager().getCurrentStage(owner);
                        Location fx = center.clone().add(
                                rng.nextInt(stage.half * 2 + 1) - stage.half + 0.5,
                                0.8,
                                rng.nextInt(stage.half * 2 + 1) - stage.half + 0.5);
                        p.getWorld().spawnParticle(Particle.CRIT, fx, 4, 0.3, 0.3, 0.3, 0.01);
                    }
                }
            }
        }, 20L, 20L);
    }

    public void stopIncomeTask() {
        if (incomeTask != null) incomeTask.cancel();
    }

    // ═══ Persistencia ═══

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "robotdata.yml");
        if (!dataFile.exists()) return;
        FileConfiguration cfg = YamlConfiguration.loadConfiguration(dataFile);
        ConfigurationSection sec = cfg.getConfigurationSection("robots");
        if (sec == null) return;
        for (String uuidStr : sec.getKeys(false)) {
            try {
                UUID owner = UUID.fromString(uuidStr);
                ConfigurationSection slots = sec.getConfigurationSection(uuidStr);
                int maxSlot = 0;
                if (slots != null) {
                    for (String s : slots.getKeys(false)) maxSlot = Math.max(maxSlot, Integer.parseInt(s));
                }
                ItemStack[] arr = new ItemStack[Math.max(1, maxSlot + 1)];
                if (slots != null) {
                    for (String s : slots.getKeys(false)) {
                        arr[Integer.parseInt(s)] = slots.getItemStack(s);
                    }
                }
                robotSlots.put(owner, arr);
            } catch (Exception e) {
                plugin.getLogger().warning("[RobotManager] Error cargando robots de " + uuidStr + ": " + e.getMessage());
            }
        }
    }

    public void saveData() {
        YamlConfiguration cfg = new YamlConfiguration();
        for (Map.Entry<UUID, ItemStack[]> entry : robotSlots.entrySet()) {
            ItemStack[] slots = entry.getValue();
            for (int i = 0; i < slots.length; i++) {
                if (slots[i] != null) {
                    cfg.set("robots." + entry.getKey() + "." + i, slots[i]);
                }
            }
        }
        try { cfg.save(dataFile); } catch (IOException e) { e.printStackTrace(); }
    }

    public Map<UUID, ItemStack[]> getAllRobots() { return robotSlots; }
}
