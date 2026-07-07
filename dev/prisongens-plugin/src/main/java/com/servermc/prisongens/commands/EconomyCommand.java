package com.servermc.prisongens.commands;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.EconomyManager;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

public class EconomyCommand implements CommandExecutor {

    private final PrisonGens plugin;

    public EconomyCommand(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("prisongens.admin")) {
            sender.sendMessage("§cNo tienes permiso.");
            return true;
        }

        if (args.length < 4) {
            sender.sendMessage("§cUso: /economy <give|remove|set> <player> <money|tokens|coins|essences> <amount>");
            return true;
        }

        String action = args[0].toLowerCase();
        Player target = Bukkit.getPlayer(args[1]);
        if (target == null) {
            sender.sendMessage("§cJugador no encontrado.");
            return true;
        }

        String typeStr = args[2].toLowerCase();
        int type = -1;
        if (typeStr.equals("money")) type = EconomyManager.MONEY;
        else if (typeStr.equals("tokens")) type = EconomyManager.TOKENS;
        else if (typeStr.equals("coins")) type = EconomyManager.COINS;
        else if (typeStr.equals("essences")) type = EconomyManager.ESSENCES;

        if (type == -1) {
            sender.sendMessage("§cTipo inválido. Usa money, tokens, coins o essences.");
            return true;
        }

        double amount;
        try {
            amount = Double.parseDouble(args[3]);
        } catch (NumberFormatException e) {
            sender.sendMessage("§cCantidad inválida.");
            return true;
        }

        EconomyManager eco = plugin.getEconomyManager();

        switch (action) {
            case "give":
                eco.addBalance(target, type, amount);
                sender.sendMessage("§aDado " + amount + " " + EconomyManager.CURRENCY_NAMES[type] + " a " + target.getName());
                break;
            case "remove":
                eco.removeBalance(target, type, amount);
                sender.sendMessage("§aRemovido " + amount + " " + EconomyManager.CURRENCY_NAMES[type] + " de " + target.getName());
                break;
            case "set":
                eco.setBalance(target, type, amount);
                sender.sendMessage("§aEstablecido " + amount + " " + EconomyManager.CURRENCY_NAMES[type] + " a " + target.getName());
                break;
            default:
                sender.sendMessage("§cUso: /economy <give|remove|set> <player> <money|tokens|coins|essences> <amount>");
                break;
        }

        return true;
    }
}
