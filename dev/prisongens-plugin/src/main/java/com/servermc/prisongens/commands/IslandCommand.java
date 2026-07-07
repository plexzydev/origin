package com.servermc.prisongens.commands;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.IslandManager;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;

import java.util.ArrayList;
import java.util.List;

public class IslandCommand implements CommandExecutor {

    private final PrisonGens plugin;

    public IslandCommand(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) return true;

        if (args.length == 0) {
            player.sendMessage("§eUso: /is <create|home|delete|settings>");
            return true;
        }

        IslandManager im = plugin.getIslandManager();

        if (args[0].equalsIgnoreCase("create")) {
            if (args.length < 2) {
                player.sendMessage("§cUso: /is create <nombre>");
                return true;
            }
            if (im.hasIsland(player)) {
                player.sendMessage("§cYa tienes una isla. Usa /is home");
                return true;
            }
            String tag = args[1];
            if (im.tagExists(tag)) {
                player.sendMessage("§cEse nombre de isla ya existe.");
                return true;
            }

            player.sendMessage("§eCreando tu isla...");
            if (im.createIsland(player, tag)) {
                player.sendMessage("§a¡Isla creada con éxito!");
                plugin.getPickaxeManager().givePickaxe(player);
                
                // Wait a bit for TP in createIsland to finish
                Bukkit.getScheduler().runTaskLater(plugin, () -> {
                    IslandManager.IslandData newIsland = im.getIsland(player);
                    if (newIsland != null) im.applyWorldBorder(player, newIsland);
                }, 25L);
            }
            return true;
        }

        if (args[0].equalsIgnoreCase("home")) {
            if (!im.hasIsland(player)) {
                player.sendMessage("§cNo tienes una isla. Usa /is create <nombre>");
                return true;
            }
            IslandManager.IslandData island = im.getIsland(player);
            player.teleport(island.getSpawn(plugin.getIslandManager().getIslandWorld()));
            im.applyWorldBorder(player, island);
            player.sendMessage("§aTeletransportado a tu isla.");
            return true;
        }

        if (args[0].equalsIgnoreCase("settings")) {
            if (!im.hasIsland(player)) {
                player.sendMessage("§cNo tienes una isla.");
                return true;
            }
            openSettingsMenu(player);
            return true;
        }

        if (args[0].equalsIgnoreCase("delete")) {
            if (!im.hasIsland(player)) {
                player.sendMessage("§cNo tienes una isla para borrar.");
                return true;
            }
            if (im.deleteIsland(player)) {
                player.sendMessage("§aTu isla ha sido borrada permanentemente.");
            } else {
                player.sendMessage("§cError al borrar la isla.");
            }
            return true;
        }

        // Add invite logic if needed
        return true;
    }

    private void openSettingsMenu(Player player) {
        Inventory inv = Bukkit.createInventory(null, 27, "§a§lAjustes de Isla");
        IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);

        ItemStack bg = createItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 27; i++) inv.setItem(i, bg);

        // Members Upgrade
        int memCost = plugin.getIslandManager().getMemberUpgradeCost(island);
        inv.setItem(10, createItem(Material.PLAYER_HEAD, "§e§lMiembros",
                "§7Límite actual: §f" + island.maxMembers,
                "§7Costo mejora: §a$" + plugin.getEconomyManager().formatBalance(memCost),
                "", "§eClick para mejorar"));

        // Hoppers Upgrade
        int hopCost = plugin.getIslandManager().getHopperUpgradeCost(island);
        inv.setItem(12, createItem(Material.HOPPER, "§7§lTolvas",
                "§7Límite actual: §f" + island.maxHoppers,
                "§7Costo mejora: §a$" + plugin.getEconomyManager().formatBalance(hopCost),
                "", "§eClick para mejorar"));

        // Regen Speed Upgrade
        int regCost = plugin.getIslandManager().getRegenUpgradeCost(island);
        inv.setItem(14, createItem(Material.CLOCK, "§b§lVelocidad de Mina",
                "§7Regeneración: §f" + (island.regenTicks / 20) + "s",
                "§7Costo mejora: §6" + plugin.getEconomyManager().formatBalance(regCost) + " tokens",
                island.regenTicks <= 100 ? "§c¡Al máximo!" : "",
                "§eClick para mejorar"));

        // Gen Capacity Upgrade
        int genCost = plugin.getIslandManager().getGenCapacityUpgradeCost(island);
        inv.setItem(16, createItem(Material.DIAMOND_PICKAXE, "§c§lCapacidad de Gens",
                "§7Límite actual: §f" + island.maxGens,
                "§7Costo mejora: §a$" + plugin.getEconomyManager().formatBalance(genCost),
                "", "§eClick para mejorar"));

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.BLOCK_CHEST_OPEN, 0.5f, 1.2f);
    }

    private ItemStack createItem(Material material, String name, String... lore) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) {
            List<String> loreList = new ArrayList<>();
            for (String line : lore) loreList.add(line);
            meta.setLore(loreList);
        }
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        item.setItemMeta(meta);
        return item;
    }
}
