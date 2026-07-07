package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.gen.GenCategory;
import com.servermc.prisongens.mine.MineManager;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

/**
 * Menú principal del Administrador de Minas (hub).
 */
public class MineAdminMenu extends Menu {

    public MineAdminMenu(PrisonGens plugin, Player viewer) {
        super(plugin, viewer, 45, "§6§l⬢ Administrador de Minas");
    }

    @Override
    protected void render() {
        fillBackground(Material.BLACK_STAINED_GLASS_PANE);
        ItemStack border = item(Material.ORANGE_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 9; i++) inventory.setItem(i, border);
        for (int i = 36; i < 45; i++) inventory.setItem(i, border);

        MineManager mm = plugin.getMineManager();
        var mine = mm.getMine(viewer.getUniqueId());
        boolean active = mine.hasActiveGen();

        // Info de la mina
        List<String> info = new ArrayList<>();
        info.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        if (active) {
            MineManager.Stage stage = mm.getCurrentStage(viewer.getUniqueId());
            info.add("§7Tamaño: §f" + stage.width() + "x" + stage.width() + "x" + mm.getMineDepth(viewer.getUniqueId()));
            info.add("§7Etapa: §f" + (mine.currentStage + 1) + "§7/§f" + mm.getStages().size());
            info.add("§7Puntos de tamaño: §f" + mm.computeSizePoints(viewer.getUniqueId()));
            info.add("§7Próximo reset: §f" + (mine.resetCountdown / 20) + "s");
            if (mm.isBlockedByIslandSize(viewer.getUniqueId())) {
                info.add("");
                info.add("§c⚠ Crecimiento bloqueado:");
                info.add("§c  ¡mejora el tamaño de tu isla!");
            }
        } else {
            info.add("§c✖ Sin GEN activo");
            info.add("§7Inserta un GEN en la sección");
            info.add("§7de GENS para crear tu mina.");
        }
        info.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        inventory.setItem(4, item(Material.FILLED_MAP, "§e§lℹ Estado de la Mina", info.toArray(new String[0])));

        // Secciones
        inventory.setItem(20, item(Material.BEACON, "§6§l⬢ GENS",
                "", "§7Inserta o retira los GENS", "§7que alimentan tu mina.", "", "§eClick para abrir"));
        inventory.setItem(22, item(Material.EXPERIENCE_BOTTLE, "§a§l⬆ Mejorar GEN",
                "", "§7Alimenta tu GEN principal con", "§7otros GENS para darle experiencia.", "", "§eClick para abrir"));
        inventory.setItem(24, item(Material.NETHER_STAR, "§b§l★ Mejoras de Isla",
                "", "§7Mejoras permanentes: tamaño de", "§7isla, capacidad, robots y más.", "", "§eClick para abrir"));

        // Tienda de GENS
        inventory.setItem(30, item(Material.EMERALD, "§a§l$ Comprar GENS",
                "", "§7Compra GENS con dinero.", "", "§eClick para abrir"));

        // Reset manual
        inventory.setItem(32, item(Material.CLOCK, "§c§l⟳ Reiniciar Mina",
                "", "§7Reinicia manualmente los bloques", "§7de tu mina ahora mismo.", "", "§eClick para reiniciar"));
    }

    @Override
    public void onClick(InventoryClickEvent event) {
        switch (event.getSlot()) {
            case 20 -> new GenSlotsMenu(plugin, viewer).open();
            case 22 -> new GenFeedMenu(plugin, viewer).open();
            case 24 -> new UpgradesMenu(plugin, viewer).open();
            case 30 -> new GenShopMenu(plugin, viewer).open();
            case 32 -> {
                var mine = plugin.getMineManager().getMine(viewer.getUniqueId());
                if (!mine.hasActiveGen()) { deny("No tienes ningún GEN activo."); return; }
                plugin.getMineManager().resetMine(viewer.getUniqueId(), false);
                mine.resetCountdown = plugin.getMineManager().getResetTicks(viewer.getUniqueId());
                success("Mina reiniciada.");
                viewer.playSound(viewer.getLocation(), Sound.BLOCK_BEACON_ACTIVATE, 0.8f, 1.4f);
                refresh();
            }
        }
    }

    /** Tienda simple de GENS: entrega el ítem físico. */
    public static class GenShopMenu extends Menu {

        private static final int[] SLOTS = {10, 11, 12, 13, 14, 15};

        public GenShopMenu(PrisonGens plugin, Player viewer) {
            super(plugin, viewer, 27, "§a§l$ Tienda de GENS");
        }

        @Override
        protected void render() {
            fillBackground(Material.BLACK_STAINED_GLASS_PANE);
            GenCategory[] cats = GenCategory.values();
            for (int i = 0; i < cats.length && i < SLOTS.length; i++) {
                GenCategory cat = cats[i];
                inventory.setItem(SLOTS[i], item(cat.icon, cat.color + "§l⬢ " + cat.display,
                        "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                        "§7Tier: " + cat.color + "★".repeat(cat.tier),
                        "§7Capacidad base: §f" + cat.baseFeedCapacity + " GENS",
                        "§7Etapa máxima: §f" + cat.maxStage,
                        "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                        "§7Precio: §a$" + plugin.getEconomyManager().formatBalance(cat.price),
                        "",
                        "§eClick para comprar"));
            }
            inventory.setItem(22, item(Material.ARROW, "§7← Volver"));
        }

        @Override
        public void onClick(InventoryClickEvent event) {
            if (event.getSlot() == 22) { new MineAdminMenu(plugin, viewer).open(); return; }
            GenCategory[] cats = GenCategory.values();
            for (int i = 0; i < cats.length && i < SLOTS.length; i++) {
                if (event.getSlot() != SLOTS[i]) continue;
                GenCategory cat = cats[i];
                if (!plugin.getEconomyManager().removeBalance(viewer,
                        com.servermc.prisongens.managers.EconomyManager.MONEY, cat.price)) {
                    deny("No tienes suficiente dinero ($" + plugin.getEconomyManager().formatBalance(cat.price) + ").");
                    return;
                }
                plugin.getEconomyManager().saveData();
                ItemStack gen = plugin.getGenItemFactory().create(cat, 1);
                viewer.getInventory().addItem(gen).values()
                        .forEach(left -> viewer.getWorld().dropItemNaturally(viewer.getLocation(), left));
                success("¡Compraste un " + cat.display + "!");
                return;
            }
        }
    }
}
