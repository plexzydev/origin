package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.gen.GenCategory;
import com.servermc.prisongens.robot.RobotCategory;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

/**
 * Estadísticas de un GEN o Robot (abierto con Shift+Click derecho
 * teniendo el ítem en la mano). Permite ver stats y renombrar.
 */
public class ItemStatsMenu extends Menu {

    private final ItemStack target;
    private final boolean isGen;

    public ItemStatsMenu(PrisonGens plugin, Player viewer, ItemStack target) {
        super(plugin, viewer, 27, plugin.getGenItemFactory().isGen(target)
                ? "§6§l⬢ Estadísticas del GEN"
                : "§b§l⚙ Estadísticas del Robot");
        this.target = target;
        this.isGen = plugin.getGenItemFactory().isGen(target);
    }

    @Override
    protected void render() {
        fillBackground(Material.BLACK_STAINED_GLASS_PANE);

        inventory.setItem(4, target.clone());

        List<String> stats = new ArrayList<>();
        stats.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        if (isGen) {
            GenCategory cat = plugin.getGenItemFactory().getCategory(target);
            int level = plugin.getGenItemFactory().getLevel(target);
            stats.add("§7Categoría: " + (cat != null ? cat.color + cat.display : "§c?"));
            stats.add("§7Tier: §f" + (cat != null ? cat.tier : "?"));
            stats.add("§7Nivel: §f" + level);
            stats.add("§7XP: §f" + plugin.getGenItemFactory().getXp(target)
                    + "§7/§f" + plugin.getGenItemFactory().xpForNextLevel(level));
            stats.add("§7Alimentados: §f" + plugin.getGenItemFactory().getFed(target)
                    + "§7/§f" + plugin.getGenItemFactory().getCapacity(target));
            stats.add("§7Etapa máxima: §f" + (cat != null ? cat.maxStage : "?"));
        } else {
            RobotCategory cat = plugin.getRobotItemFactory().getCategory(target);
            int level = plugin.getRobotItemFactory().getLevel(target);
            stats.add("§7Categoría: " + (cat != null ? cat.color + cat.display : "§c?"));
            stats.add("§7Tier: §f" + (cat != null ? cat.tier : "?"));
            stats.add("§7Nivel: §f" + level + "§7/§f" + (cat != null ? cat.maxLevel : "?"));
            if (cat != null) {
                stats.add("§7Ingresos: §a$" + String.format("%.1f", cat.moneyPerSec * level) + "§7/s");
                stats.add("§7Prob. Tokens: §6" + String.format("%.1f", cat.tokenChance * 100 * level) + "%§7/s");
            }
        }
        stats.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        inventory.setItem(11, item(Material.FILLED_MAP, "§e§lℹ Información", stats.toArray(new String[0])));

        inventory.setItem(15, item(Material.NAME_TAG, "§d§l✎ Renombrar",
                "", "§7Dale un nombre personalizado", "§7a este " + (isGen ? "GEN" : "Robot") + ".",
                "", "§eClick para escribir el nombre"));

        inventory.setItem(22, item(Material.BARRIER, "§c§lCerrar"));
    }

    @Override
    public void onClick(InventoryClickEvent event) {
        switch (event.getSlot()) {
            case 22 -> viewer.closeInventory();
            case 15 -> plugin.getMenuManager().requestChatInput(viewer,
                    "Escribe el nuevo nombre para tu " + (isGen ? "GEN" : "Robot") + ":",
                    name -> {
                        if (name.length() > 24) {
                            viewer.sendMessage("§c§l✖ §7El nombre no puede superar los 24 caracteres.");
                            return;
                        }
                        if (isGen) plugin.getGenItemFactory().setCustomName(target, name);
                        else plugin.getRobotItemFactory().setCustomName(target, name);
                        viewer.sendMessage("§a§l✓ §7Renombrado a §f" + name + "§7.");
                    });
        }
    }
}
