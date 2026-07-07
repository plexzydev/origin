package dev.plexzy.prisongens.robots;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.gen.GenData;
import dev.plexzy.prisongens.utils.EconomyUtil;
import org.bukkit.Bukkit;
import org.bukkit.NamespacedKey;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.persistence.PersistentDataContainer;
import org.bukkit.persistence.PersistentDataType;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

/**
 * Gestiona todos los robots activos en el servidor.
 * Cada isla puede tener múltiples robots insertados.
 */
public class RobotManager {

    private final PrisonGens plugin;
    private final RobotItemFactory factory;

    // islandId -> lista de datos de robot activo
    private final Map<UUID, List<RobotData>> activeRobots = new ConcurrentHashMap<>();

    // Tick acumulados por robot para respetar su speed
    private final Map<String, Double> tickAccumulator = new ConcurrentHashMap<>();

    private File dataFile;
    private FileConfiguration dataConfig;

    public RobotManager(PrisonGens plugin) {
        this.plugin  = plugin;
        this.factory = new RobotItemFactory(plugin);
        loadData();
    }

    // ── Insertar / Retirar ────────────────────────────────────────────────────

    /**
     * Inserta un robot en la isla del jugador.
     * @return true si se insertó correctamente.
     */
    public boolean insertRobot(Player player, UUID islandId, ItemStack robotItem) {
        if (!factory.isRobot(robotItem)) return false;

        PersistentDataContainer pdc = robotItem.getItemMeta().getPersistentDataContainer();
        String robotId = pdc.get(nkey(RobotItemFactory.KEY_ROBOT_ID), PersistentDataType.STRING);

        // Comprobar si ya está activo
        if (isRobotActive(robotId)) {
            player.sendMessage("§c✘ Este robot ya está activo en alguna isla.");
            return false;
        }

        // Límite de robots por isla
        int maxRobots = plugin.getUpgradeManager().getRobotSlots(islandId);
        List<RobotData> list = activeRobots.computeIfAbsent(islandId, k -> new ArrayList<>());
        if (list.size() >= maxRobots) {
            player.sendMessage("§c✘ Has alcanzado el límite de robots (" + maxRobots + "). "
                    + "§7Mejora los §eSlots de Robots §7en las mejoras de isla.");
            return false;
        }

        // Construir RobotData
        RobotData data = RobotData.fromItem(robotItem, plugin);
        data.setIslandId(islandId);
        data.setOwnerUuid(player.getUniqueId());
        list.add(data);

        // Quitar del inventario
        robotItem.setAmount(0);

        player.sendMessage("§a✔ Robot §f" + data.getCategory().getColoredName()
                + " §aNivel §f" + data.getLevel() + " §ainsertado correctamente.");
        player.playSound(player.getLocation(),
                org.bukkit.Sound.BLOCK_ANVIL_USE, 0.7f, 1.3f);

        return true;
    }

    /**
     * Retira un robot por su ID y lo devuelve como ítem al jugador.
     */
    public boolean withdrawRobot(Player player, UUID islandId, String robotId) {
        List<RobotData> list = activeRobots.get(islandId);
        if (list == null) return false;

        RobotData toRemove = list.stream()
                .filter(r -> r.getRobotId().equals(robotId))
                .findFirst().orElse(null);

        if (toRemove == null) {
            player.sendMessage("§c✘ No se encontró ese robot.");
            return false;
        }

        list.remove(toRemove);
        tickAccumulator.remove(robotId);

        // Reconstruir ítem con stats actualizados
        ItemStack item = toRemove.toItem(plugin);
        player.getInventory().addItem(item);

        player.sendMessage("§a✔ Robot retirado y devuelto a tu inventario.");
        player.playSound(player.getLocation(),
                org.bukkit.Sound.ENTITY_ITEM_PICKUP, 1f, 1.2f);
        return true;
    }

    // ── Tick de Robots ────────────────────────────────────────────────────────

    /**
     * Llamado cada segundo por el scheduler principal.
     * Procesa todos los robots activos.
     */
    public void tickAllRobots() {
        for (Map.Entry<UUID, List<RobotData>> entry : activeRobots.entrySet()) {
            UUID islandId = entry.getKey();
            GenData activeGen = plugin.getGenManager().getActiveGen(islandId);
            if (activeGen == null) continue;

            // ¿El dueño está online? (requerido a menos que offline mode esté activado)
            boolean offlineMode = plugin.getConfig().getBoolean("robots.offline-mode", false);
            UUID ownerUuid = plugin.getIslandManager().getIslandOwner(islandId);
            Player owner = (ownerUuid != null) ? Bukkit.getPlayer(ownerUuid) : null;
            if (!offlineMode && owner == null) continue;

            for (RobotData robot : entry.getValue()) {
                tickRobot(robot, activeGen, owner);
            }
        }
    }

    private void tickRobot(RobotData robot, GenData gen, Player owner) {
        String rid = robot.getRobotId();

        // Acumular ticks para respetar speed
        double acc = tickAccumulator.getOrDefault(rid, 0.0) + robot.getSpeed();
        if (acc < 1.0) {
            tickAccumulator.put(rid, acc);
            return;
        }
        tickAccumulator.put(rid, acc - Math.floor(acc));

        int actions = (int) Math.floor(acc);
        for (int i = 0; i < actions; i++) {
            executeRobotAction(robot, gen, owner);
        }
    }

    private void executeRobotAction(RobotData robot, GenData gen, Player owner) {
        double eff    = robot.getEfficiency();
        double money  = robot.getMoneyPerAction() * eff;
        long tokens   = (long) (robot.getTokensPerAction() * eff);

        // Dar dinero
        if (owner != null && owner.isOnline()) {
            EconomyUtil.deposit(owner, money);

            // Tokens via PDC del jugador
            plugin.getGenManager().addTokens(owner, tokens);
        } else {
            // Modo offline: guardar en buffer
            robot.addOfflineMoney(money);
            robot.addOfflineTokens(tokens);
        }

        // XP al robot
        robot.addXp(1L);
        checkRobotLevelUp(robot);
    }

    private void checkRobotLevelUp(RobotData robot) {
        long needed = robot.getCategory().xpToLevel(robot.getLevel());
        if (robot.getXp() >= needed) {
            robot.setLevel(robot.getLevel() + 1);
            robot.setXp(robot.getXp() - needed);

            // Mejora de stats al subir nivel
            robot.setSpeed(robot.getSpeed() + 0.05);
            robot.setEfficiency(robot.getEfficiency() + 0.02);

            // Notificación si el dueño está online
            Player owner = Bukkit.getPlayer(robot.getOwnerUuid());
            if (owner != null) {
                owner.sendMessage("§6⚙ §e¡Tu robot §f" + robot.getCategory().getDisplayName()
                        + " §esubió al nivel §f" + robot.getLevel() + "§e!");
                owner.playSound(owner.getLocation(),
                        org.bukkit.Sound.UI_TOAST_CHALLENGE_COMPLETE, 0.6f, 1.5f);
            }
        }
    }

    // ── Mejorar Robot ─────────────────────────────────────────────────────────

    /**
     * Mejora una estadística del robot usando dinero/tokens.
     */
    public boolean upgradeRobotStat(Player player, UUID islandId,
                                    String robotId, RobotStat stat) {
        RobotData robot = getRobotData(islandId, robotId);
        if (robot == null) {
            player.sendMessage("§c✘ Robot no encontrado.");
            return false;
        }

        double cost  = stat.getCost(robot.getUpgradeTier(stat));
        long tcost   = stat.getTokenCost(robot.getUpgradeTier(stat));

        if (!EconomyUtil.has(player, cost)) {
            player.sendMessage("§c✘ Necesitas §f$" + String.format("%.0f", cost)
                    + " §cpara esta mejora.");
            return false;
        }
        if (!plugin.getGenManager().hasTokens(player, tcost)) {
            player.sendMessage("§c✘ Necesitas §f" + tcost + " §cTokens para esta mejora.");
            return false;
        }

        EconomyUtil.withdraw(player, cost);
        plugin.getGenManager().removeTokens(player, tcost);
        robot.incrementUpgradeTier(stat);
        stat.apply(robot);

        player.sendMessage("§a✔ §f" + stat.getDisplayName()
                + " §amejorado al nivel §f" + robot.getUpgradeTier(stat) + "§a.");
        player.playSound(player.getLocation(),
                org.bukkit.Sound.BLOCK_ENCHANTMENT_TABLE_USE, 0.8f, 1.2f);
        return true;
    }

    // ── Persistencia ─────────────────────────────────────────────────────────

    private void loadData() {
        dataFile = new File(plugin.getDataFolder(), "robots.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) {
                plugin.getLogger().severe("No se pudo crear robots.yml");
            }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);

        for (String islandStr : dataConfig.getKeys(false)) {
            UUID islandId = UUID.fromString(islandStr);
            List<RobotData> list = new ArrayList<>();
            if (dataConfig.isConfigurationSection(islandStr)) {
                for (String robotId : dataConfig.getConfigurationSection(islandStr).getKeys(false)) {
                    try {
                        RobotData rd = RobotData.fromConfig(
                                dataConfig.getConfigurationSection(islandStr + "." + robotId), plugin);
                        list.add(rd);
                    } catch (Exception e) {
                        plugin.getLogger().log(Level.WARNING,
                                "Error cargando robot " + robotId, e);
                    }
                }
            }
            activeRobots.put(islandId, list);
        }
    }

    public void saveAll() {
        // Limpiar config
        for (String k : dataConfig.getKeys(false)) dataConfig.set(k, null);

        for (Map.Entry<UUID, List<RobotData>> entry : activeRobots.entrySet()) {
            String base = entry.getKey().toString();
            for (RobotData rd : entry.getValue()) {
                rd.saveToConfig(dataConfig, base + "." + rd.getRobotId());
            }
        }

        try { dataConfig.save(dataFile); }
        catch (IOException e) {
            plugin.getLogger().log(Level.SEVERE, "Error guardando robots.yml", e);
        }
    }

    public void shutdown() {
        saveAll();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    public RobotData getRobotData(UUID islandId, String robotId) {
        List<RobotData> list = activeRobots.get(islandId);
        if (list == null) return null;
        return list.stream().filter(r -> r.getRobotId().equals(robotId)).findFirst().orElse(null);
    }

    public List<RobotData> getRobots(UUID islandId) {
        return activeRobots.getOrDefault(islandId, new ArrayList<>());
    }

    public boolean isRobotActive(String robotId) {
        return activeRobots.values().stream()
                .flatMap(Collection::stream)
                .anyMatch(r -> r.getRobotId().equals(robotId));
    }

    public RobotItemFactory getFactory() { return factory; }

    private NamespacedKey nkey(String k) {
        return new NamespacedKey(plugin, k);
    }
}
