package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.EconomyManager;
import com.servermc.prisongens.robot.RobotCategory;
import com.servermc.prisongens.robot.RobotManager;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

/**
 * Menú del Administrador de Robots.
 * Click izquierdo sobre robot activo → retirar (conserva stats).
 * Click derecho sobre robot activo → mejorar nivel (dinero).
 * Click sobre slot libre → insertar el primer robot del inventario.
 */
public class RobotAdminMenu extends Menu {

    private static final int[] SLOT_POSITIONS = {10, 11, 12, 13, 14, 15, 16, 19};
    private static final int INFO_SLOT = 4;
    private static final int SHOP_SLOT = 31;
    private static final int CLOSE_SLOT = 40;

    public RobotAdminMenu(PrisonGens plugin, Player viewer) {
        super(plugin, viewer, 45, "§b§l⚙ Administrador de Robots");
    }

    @Override
    protected void render() {
        fillBackground(Material.BLACK_STAINED_GLASS_PANE);
        ItemStack border = item(Material.LIGHT_BLUE_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 9; i++) inventory.setItem(i, border);
        for (int i = 36; i < 45; i++) inventory.setItem(i, border);

        RobotManager rm = plugin.getRobotManager();
        ItemStack[] slots = rm.getSlots(viewer.getUniqueId());
        int maxSlots = rm.getMaxSlots(viewer.getUniqueId());
        var mine = plugin.getMineManager().getMine(viewer.getUniqueId());

        // Info
        List<String> info = new ArrayList<>();
        info.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        info.add("§7Robots activos: §f" + rm.countActive(viewer.getUniqueId()) + "§7/§f" + maxSlots);
        info.add("§7Etapa de mina: §f" + (mine.hasActiveGen() ? (mine.currentStage + 1) : "§csin mina"));
        info.add("");
        info.add("§7Los robots trabajan en tu mina y");
        info.add("§7generan §aDinero §7y §6Tokens §7por segundo.");
        info.add("§7Tiers altos requieren minas más grandes.");
        info.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        inventory.setItem(INFO_SLOT, item(Material.FILLED_MAP, "§e§lℹ Robots", info.toArray(new String[0])));

        // Slots
        for (int i = 0; i < SLOT_POSITIONS.length; i++) {
            if (i < slots.length) {
                ItemStack robot = slots[i];
                if (robot != null) {
                    ItemStack display = robot.clone();
                    var meta = display.getItemMeta();
                    var lore = meta.hasLore() ? new java.util.ArrayList<>(meta.getLore()) : new java.util.ArrayList<String>();
                    lore.add("");
                    long cost = plugin.getRobotItemFactory().upgradeCost(robot);
                    RobotCategory cat = plugin.getRobotItemFactory().getCategory(robot);
                    int level = plugin.getRobotItemFactory().getLevel(robot);
                    if (cat != null && level < cat.maxLevel) {
                        lore.add("§eClick derecho §7mejorar §8($" + plugin.getEconomyManager().formatBalance(cost) + ")");
                    } else {
                        lore.add("§a§l✓ Nivel máximo");
                    }
                    lore.add("§eClick izquierdo §7retirar");
                    meta.setLore(lore);
                    display.setItemMeta(meta);
                    inventory.setItem(SLOT_POSITIONS[i], display);
                } else {
                    inventory.setItem(SLOT_POSITIONS[i], item(Material.LIME_STAINED_GLASS_PANE,
                            "§a§l+ Slot Libre",
                            "", "§7Ten un Robot en tu inventario", "§7y haz click aquí para insertarlo."));
                }
            } else {
                inventory.setItem(SLOT_POSITIONS[i], item(Material.RED_STAINED_GLASS_PANE,
                        "§c§l✖ Slot Bloqueado",
                        "", "§7Desbloquea más slots con la", "§7mejora §fSlots de Robots§7."));
            }
        }

        inventory.setItem(SHOP_SLOT, item(Material.EMERALD, "§a§l$ Comprar Robots",
                "", "§7Compra robots con dinero.", "", "§eClick para abrir"));
        inventory.setItem(CLOSE_SLOT, item(Material.BARRIER, "§c§lCerrar"));
    }

    @Override
    public void onClick(InventoryClickEvent event) {
        int slot = event.getSlot();
        if (slot == CLOSE_SLOT) { viewer.closeInventory(); return; }
        if (slot == SHOP_SLOT) { new RobotShopMenu(plugin, viewer).open(); return; }

        int slotIndex = -1;
        for (int i = 0; i < SLOT_POSITIONS.length; i++) {
            if (SLOT_POSITIONS[i] == slot) { slotIndex = i; break; }
        }
        if (slotIndex == -1) return;

        RobotManager rm = plugin.getRobotManager();
        ItemStack[] slots = rm.getSlots(viewer.getUniqueId());
        if (slotIndex >= slots.length) {
            deny("Este slot está bloqueado. Compra la mejora Slots de Robots.");
            return;
        }

        ItemStack current = slots[slotIndex];

        if (current != null) {
            if (event.isRightClick()) {
                upgradeRobot(current);
                return;
            }
            // Retirar
            if (viewer.getInventory().firstEmpty() == -1) {
                deny("Tu inventario está lleno.");
                return;
            }
            ItemStack out = rm.withdrawRobot(viewer.getUniqueId(), slotIndex);
            if (out != null) {
                viewer.getInventory().addItem(out);
                success("Robot retirado. Conserva todas sus estadísticas.");
                viewer.playSound(viewer.getLocation(), Sound.ENTITY_ITEM_PICKUP, 0.8f, 0.9f);
            }
            refresh();
            return;
        }

        // Insertar: buscar el primer robot del inventario
        ItemStack toInsert = null;
        for (ItemStack it : viewer.getInventory().getContents()) {
            if (it != null && plugin.getRobotItemFactory().isRobot(it)) { toInsert = it; break; }
        }
        if (toInsert == null) {
            deny("No tienes ningún Robot. Cómpralo en la tienda de Robots.");
            return;
        }

        if (!rm.canUseRobot(viewer.getUniqueId(), toInsert)) {
            RobotCategory cat = plugin.getRobotItemFactory().getCategory(toInsert);
            int req = cat != null ? rm.requiredStage(cat) : 0;
            deny("Tu mina necesita al menos la etapa " + (req + 1) + " para usar este robot.");
            return;
        }

        ItemStack single = toInsert.clone();
        single.setAmount(1);
        slots[slotIndex] = single;
        toInsert.setAmount(toInsert.getAmount() - 1);
        rm.saveData();
        success("¡Robot insertado! Empezará a trabajar en tu mina.");
        viewer.playSound(viewer.getLocation(), Sound.BLOCK_PISTON_EXTEND, 0.9f, 1.4f);
        refresh();
    }

    private void upgradeRobot(ItemStack robot) {
        RobotCategory cat = plugin.getRobotItemFactory().getCategory(robot);
        int level = plugin.getRobotItemFactory().getLevel(robot);
        if (cat == null) return;
        if (level >= cat.maxLevel) {
            deny("Este robot ya está al nivel máximo.");
            return;
        }
        long cost = plugin.getRobotItemFactory().upgradeCost(robot);
        if (!plugin.getEconomyManager().removeBalance(viewer, EconomyManager.MONEY, cost)) {
            deny("No tienes suficiente dinero ($" + plugin.getEconomyManager().formatBalance(cost) + ").");
            return;
        }
        plugin.getEconomyManager().saveData();
        plugin.getRobotItemFactory().setLevel(robot, level + 1);
        plugin.getRobotManager().saveData();
        success("Robot mejorado a nivel " + (level + 1) + ".");
        viewer.playSound(viewer.getLocation(), Sound.BLOCK_ANVIL_USE, 0.8f, 1.5f);
        refresh();
    }

    /** Tienda simple de Robots: entrega el ítem físico. */
    public static class RobotShopMenu extends Menu {

        private static final int[] SLOTS = {10, 11, 12, 13, 14};

        public RobotShopMenu(PrisonGens plugin, Player viewer) {
            super(plugin, viewer, 27, "§a§l$ Tienda de Robots");
        }

        @Override
        protected void render() {
            fillBackground(Material.BLACK_STAINED_GLASS_PANE);
            RobotCategory[] cats = RobotCategory.values();
            for (int i = 0; i < cats.length && i < SLOTS.length; i++) {
                RobotCategory cat = cats[i];
                int req = plugin.getRobotManager().requiredStage(cat);
                inventory.setItem(SLOTS[i], item(cat.icon, cat.color + "§l⚙ " + cat.display,
                        "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                        "§7Tier: " + cat.color + "★".repeat(cat.tier),
                        "§7Ingresos base: §a$" + String.format("%.1f", cat.moneyPerSec) + "§7/s",
                        "§7Nivel máximo: §f" + cat.maxLevel,
                        "§7Requiere mina etapa: §f" + (req + 1),
                        "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                        "§7Precio: §a$" + plugin.getEconomyManager().formatBalance(cat.price),
                        "",
                        "§eClick para comprar"));
            }
            inventory.setItem(22, item(Material.ARROW, "§7← Volver"));
        }

        @Override
        public void onClick(InventoryClickEvent event) {
            if (event.getSlot() == 22) { new RobotAdminMenu(plugin, viewer).open(); return; }
            RobotCategory[] cats = RobotCategory.values();
            for (int i = 0; i < cats.length && i < SLOTS.length; i++) {
                if (event.getSlot() != SLOTS[i]) continue;
                RobotCategory cat = cats[i];
                if (!plugin.getEconomyManager().removeBalance(viewer, EconomyManager.MONEY, cat.price)) {
                    deny("No tienes suficiente dinero ($" + plugin.getEconomyManager().formatBalance(cat.price) + ").");
                    return;
                }
                plugin.getEconomyManager().saveData();
                ItemStack robot = plugin.getRobotItemFactory().create(cat, 1);
                viewer.getInventory().addItem(robot).values()
                        .forEach(left -> viewer.getWorld().dropItemNaturally(viewer.getLocation(), left));
                success("¡Compraste un " + cat.display + "!");
                return;
            }
        }
    }
}
