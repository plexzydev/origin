package dev.plexzy.prisongens.robots.menu;

import dev.plexzy.prisongens.PrisonGens;
import dev.plexzy.prisongens.robots.RobotData;
import dev.plexzy.prisongens.robots.RobotStat;
import dev.plexzy.prisongens.utils.GuiUtil;
import dev.plexzy.prisongens.utils.ItemBuilder;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCloseEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * GUI del NPC Administrador de Robots.
 * Permite insertar, retirar y mejorar robots.
 */
public class RobotAdminMenu implements Listener {

    private final PrisonGens plugin;

    // playerUUID -> inventario abierto de robots
    private final Map<UUID, Inventory> openMenus = new HashMap<>();
    private final Map<UUID, UUID> islandContext  = new HashMap<>();

    private static final int SIZE = 54;

    // Slots de los robots (máximo 7 slots visibles)
    private static final int[] ROBOT_SLOTS = {20, 21, 22, 23, 24, 29, 30};

    public RobotAdminMenu(PrisonGens plugin) {
        this.plugin = plugin;
        Bukkit.getPluginManager().registerEvents(this, plugin);
    }

    public void open(Player player, UUID islandId) {
        Inventory inv = Bukkit.createInventory(null, SIZE,
                ChatColor.DARK_GRAY + "⚙ " + ChatColor.AQUA + "Administrador de Robots");

        islandContext.put(player.getUniqueId(), islandId);

        // Decoración
        GuiUtil.fillBorders(inv, GuiUtil.DARK_GLASS);

        // Slots de robots
        List<RobotData> robots = plugin.getRobotManager().getRobots(islandId);
        int maxSlots = plugin.getUpgradeManager().getRobotSlots(islandId);

        for (int i = 0; i < ROBOT_SLOTS.length; i++) {
            int slot = ROBOT_SLOTS[i];
            if (i >= maxSlots) {
                // Slot bloqueado
                inv.setItem(slot, ItemBuilder.of(Material.BARRIER)
                        .name(ChatColor.RED + "🔒 Slot Bloqueado")
                        .lore(ChatColor.GRAY + "Mejora los Slots de Robots",
                              ChatColor.GRAY + "en las mejoras de isla para desbloquear.")
                        .build());
            } else if (i < robots.size()) {
                // Robot activo
                RobotData rd = robots.get(i);
                inv.setItem(slot, buildRobotSlotItem(rd));
            } else {
                // Slot vacío
                inv.setItem(slot, ItemBuilder.of(Material.LIME_STAINED_GLASS_PANE)
                        .name(ChatColor.GREEN + "➕ Slot Vacío")
                        .lore(ChatColor.GRAY + "Arrastra un Robot aquí",
                              ChatColor.GRAY + "desde tu inventario para insertarlo.")
                        .build());
            }
        }

        // Botón de mejoras de robot (slot 40)
        inv.setItem(40, ItemBuilder.of(Material.ANVIL)
                .name(ChatColor.YELLOW + "🔧 Mejorar Robot")
                .lore(ChatColor.GRAY + "Selecciona un robot activo",
                      ChatColor.GRAY + "para ver sus opciones de mejora.")
                .build());

        // Info
        inv.setItem(4, ItemBuilder.of(Material.HOPPER)
                .name(ChatColor.AQUA + "ℹ Información")
                .lore(ChatColor.GRAY + "Robots activos: " + ChatColor.WHITE + robots.size()
                        + ChatColor.GRAY + "/" + maxSlots,
                      "",
                      ChatColor.GRAY + "Los robots trabajan automáticamente",
                      ChatColor.GRAY + "dentro de tu mina activa.")
                .build());

        openMenus.put(player.getUniqueId(), inv);
        player.openInventory(inv);
    }

    private void openUpgradeMenu(Player player, UUID islandId, RobotData robot) {
        Inventory inv = Bukkit.createInventory(null, 54,
                ChatColor.DARK_GRAY + "🔧 " + ChatColor.AQUA + "Mejorar Robot");

        GuiUtil.fillBorders(inv, GuiUtil.DARK_GLASS);

        RobotStat[] stats = RobotStat.values();
        int[] statSlots = {20, 21, 22, 23, 24, 29, 30};

        for (int i = 0; i < stats.length && i < statSlots.length; i++) {
            RobotStat stat = stats[i];
            int tier = robot.getUpgradeTier(stat);
            double cost  = stat.getCost(tier);
            long tcost   = stat.getTokenCost(tier);

            inv.setItem(statSlots[i], ItemBuilder.of(Material.EXPERIENCE_BOTTLE)
                    .name(ChatColor.YELLOW + stat.getDisplayName())
                    .lore(ChatColor.GRAY + "Nivel actual: " + ChatColor.WHITE + tier,
                          ChatColor.GRAY + "Costo: " + ChatColor.GREEN + "$"
                                  + String.format("%.0f", cost),
                          ChatColor.GRAY + "Tokens: " + ChatColor.GOLD + tcost,
                          "",
                          ChatColor.YELLOW + "Click para mejorar")
                    .build());
        }

        // Botón volver
        inv.setItem(49, ItemBuilder.of(Material.ARROW)
                .name(ChatColor.RED + "← Volver")
                .build());

        // Info del robot
        inv.setItem(4, robot.toItem(plugin));

        // Contexto temporal: marcar que este menú es de upgrade de robot
        islandContext.put(player.getUniqueId(), islandId);
        openMenus.put(player.getUniqueId(), inv);
        player.openInventory(inv);
    }

    @EventHandler
    public void onClick(InventoryClickEvent e) {
        if (!(e.getWhoClicked() instanceof Player player)) return;
        Inventory menu = openMenus.get(player.getUniqueId());
        if (menu == null || !e.getInventory().equals(menu)) return;

        e.setCancelled(true);

        UUID islandId = islandContext.get(player.getUniqueId());
        if (islandId == null) return;

        String title = e.getView().getTitle();
        ItemStack clicked = e.getCurrentItem();
        if (clicked == null || clicked.getType() == Material.AIR) return;

        // ── Menú principal ────────────────────────────────────────────────────
        if (title.contains("Administrador de Robots")) {
            // Click en slot de robot activo → abrir opciones
            for (int i = 0; i < ROBOT_SLOTS.length; i++) {
                if (e.getRawSlot() == ROBOT_SLOTS[i]) {
                    List<RobotData> robots = plugin.getRobotManager().getRobots(islandId);
                    if (i < robots.size()) {
                        openRobotOptions(player, islandId, robots.get(i));
                    } else {
                        // Slot vacío: intentar insertar robot del inventario del jugador
                        ItemStack cursor = e.getCursor();
                        if (plugin.getRobotManager().getFactory().isRobot(cursor)) {
                            plugin.getRobotManager().insertRobot(player, islandId, cursor);
                            open(player, islandId); // Refrescar
                        }
                    }
                    return;
                }
            }

            // Botón mejorar
            if (e.getRawSlot() == 40) {
                player.sendMessage(ChatColor.YELLOW + "Haz click en un robot activo primero.");
            }
        }

        // ── Menú de opciones de robot ─────────────────────────────────────────
        if (title.contains("Opciones de Robot")) {
            handleRobotOptions(e, player, islandId, clicked);
        }

        // ── Menú de mejoras de robot ──────────────────────────────────────────
        if (title.contains("Mejorar Robot")) {
            if (e.getRawSlot() == 49) { open(player, islandId); return; }
            handleUpgradeClick(e, player, islandId);
        }
    }

    private void openRobotOptions(Player player, UUID islandId, RobotData robot) {
        Inventory inv = Bukkit.createInventory(null, 27,
                ChatColor.DARK_GRAY + "⚙ Opciones de Robot");

        GuiUtil.fillBorders(inv, GuiUtil.DARK_GLASS);

        // Vista del robot
        inv.setItem(4, robot.toItem(plugin));

        // Opción: Retirar
        inv.setItem(11, ItemBuilder.of(Material.ENDER_PEARL)
                .name(ChatColor.RED + "📤 Retirar Robot")
                .lore(ChatColor.GRAY + "El robot volverá a tu inventario",
                      ChatColor.GRAY + "con todas sus estadísticas.")
                .build());

        // Opción: Mejorar
        inv.setItem(13, ItemBuilder.of(Material.ANVIL)
                .name(ChatColor.YELLOW + "🔧 Mejorar Estadísticas")
                .lore(ChatColor.GRAY + "Gasta dinero y Tokens para",
                      ChatColor.GRAY + "mejorar las stats del robot.")
                .build());

        // Botón volver
        inv.setItem(22, ItemBuilder.of(Material.ARROW)
                .name(ChatColor.RED + "← Volver")
                .build());

        // Guardar contexto: robotId en nombre del inventory
        openMenus.put(player.getUniqueId(), inv);
        islandContext.put(player.getUniqueId(), islandId);
        // Guardar robotId en un mapa temporal
        tempRobotId.put(player.getUniqueId(), robot.getRobotId());

        player.openInventory(inv);
    }

    private final Map<UUID, String> tempRobotId = new HashMap<>();

    private void handleRobotOptions(InventoryClickEvent e, Player player,
                                    UUID islandId, ItemStack clicked) {
        String rid = tempRobotId.get(player.getUniqueId());
        if (rid == null) return;

        switch (e.getRawSlot()) {
            case 11 -> { // Retirar
                if (plugin.getRobotManager().withdrawRobot(player, islandId, rid)) {
                    player.closeInventory();
                }
            }
            case 13 -> { // Mejorar
                RobotData rd = plugin.getRobotManager().getRobotData(islandId, rid);
                if (rd != null) openUpgradeMenu(player, islandId, rd);
            }
            case 22 -> open(player, islandId); // Volver
        }
    }

    private void handleUpgradeClick(InventoryClickEvent e, Player player, UUID islandId) {
        String rid = tempRobotId.get(player.getUniqueId());
        if (rid == null) return;
        RobotData robot = plugin.getRobotManager().getRobotData(islandId, rid);
        if (robot == null) return;

        int[] statSlots = {20, 21, 22, 23, 24, 29, 30};
        RobotStat[] stats = RobotStat.values();

        for (int i = 0; i < statSlots.length && i < stats.length; i++) {
            if (e.getRawSlot() == statSlots[i]) {
                plugin.getRobotManager().upgradeRobotStat(player, islandId, rid, stats[i]);
                openUpgradeMenu(player, islandId, robot); // Refrescar
                return;
            }
        }
    }

    @EventHandler
    public void onClose(InventoryCloseEvent e) {
        openMenus.remove(e.getPlayer().getUniqueId());
    }

    private ItemStack buildRobotSlotItem(RobotData rd) {
        return ItemBuilder.of(Material.PAPER)
                .name(rd.getCategory().getColor() + "⚙ " + rd.getCategory().getDisplayName()
                        + ChatColor.DARK_GRAY + " [Nv." + rd.getLevel() + "]")
                .lore(ChatColor.GRAY + "Eficiencia: " + ChatColor.AQUA
                              + String.format("%.1fx", rd.getEfficiency()),
                      ChatColor.GRAY + "Velocidad: "  + ChatColor.AQUA
                              + String.format("%.1f", rd.getSpeed()) + "/s",
                      ChatColor.GRAY + "Radio: "      + ChatColor.AQUA + rd.getRadius() + " bl",
                      "",
                      ChatColor.YELLOW + "Click para opciones")
                .build();
    }
}
