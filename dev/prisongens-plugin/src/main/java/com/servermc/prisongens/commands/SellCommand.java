package com.servermc.prisongens.commands;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.EconomyManager;
import org.bukkit.Material;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.HashMap;
import java.util.Map;

public class SellCommand implements CommandExecutor {

    private final PrisonGens plugin;
    private final Map<Material, Double> prices = new HashMap<>();

    public SellCommand(PrisonGens plugin) {
        this.plugin = plugin;
        prices.put(Material.COBBLESTONE, 1.0);
        prices.put(Material.RAW_IRON, 5.0);
        prices.put(Material.RAW_GOLD, 15.0);
        prices.put(Material.DIAMOND, 50.0);
        prices.put(Material.EMERALD, 150.0);
        prices.put(Material.NETHERITE_SCRAP, 500.0);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) return true;

        double total = 0;
        int itemsSold = 0;

        for (int i = 0; i < player.getInventory().getSize(); i++) {
            ItemStack item = player.getInventory().getItem(i);
            if (item != null && prices.containsKey(item.getType())) {
                double price = prices.get(item.getType());
                int amount = item.getAmount();
                total += price * amount;
                itemsSold += amount;
                player.getInventory().setItem(i, null);
            }
        }

        if (total > 0) {
            plugin.getEconomyManager().addBalance(player, EconomyManager.MONEY, total);
            player.sendMessage("§a§l+$" + plugin.getEconomyManager().formatBalance(total) + " §7por vender " + itemsSold + " items.");
        } else {
            player.sendMessage("§cNo tienes items que se puedan vender en tu inventario.");
        }

        return true;
    }
}
