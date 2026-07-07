package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.managers.CoinManager;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * /coins - Admin commands to manage lobby coins.
 * 
 * Usage:
 *   /coins give <player> <amount>   - Give coins to a player
 *   /coins remove <player> <amount> - Remove coins from a player
 *   /coins set <player> <amount>    - Set a player's coins
 *   /coins check <player>           - Check a player's balance
 *   /coins balance                  - Check your own balance
 */
public class CoinsCommand implements CommandExecutor {

    private final LobbyCore plugin;

    private static final TextColor ORANGE = TextColor.color(255, 140, 0);
    private static final TextColor GOLD = TextColor.color(255, 200, 50);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);

    public CoinsCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        CoinManager coinManager = plugin.getCoinManager();

        // /coins balance (any player)
        if (args.length == 0 || (args.length == 1 && args[0].equalsIgnoreCase("balance"))) {
            if (!(sender instanceof Player player)) {
                sender.sendMessage("§cEste comando solo puede ser usado por jugadores.");
                return true;
            }
            int balance = coinManager.getCoins(player);
            player.sendMessage(Component.empty()
                    .append(Component.text(" 🪙 ", GOLD))
                    .append(Component.text("Tus monedas: ", GRAY))
                    .append(Component.text(String.valueOf(balance), GOLD).decoration(TextDecoration.BOLD, true)));
            return true;
        }

        // Admin commands
        String action = args[0].toLowerCase();

        // /coins check <player>
        if (action.equals("check") && args.length >= 2) {
            if (!sender.hasPermission("lobby.admin")) {
                sender.sendMessage("§cNo tienes permiso.");
                return true;
            }
            Player target = Bukkit.getPlayer(args[1]);
            if (target == null) {
                sender.sendMessage("§c§l✖ §7Jugador no encontrado.");
                return true;
            }
            int balance = coinManager.getCoins(target);
            sender.sendMessage(Component.empty()
                    .append(Component.text(" 🪙 ", GOLD))
                    .append(Component.text("Monedas de ", GRAY))
                    .append(Component.text(target.getName(), ORANGE))
                    .append(Component.text(": ", GRAY))
                    .append(Component.text(String.valueOf(balance), GOLD).decoration(TextDecoration.BOLD, true)));
            return true;
        }

        // /coins give|remove|set <player> <amount>
        if (args.length < 3) {
            sendUsage(sender);
            return true;
        }

        if (!sender.hasPermission("lobby.admin")) {
            sender.sendMessage("§cNo tienes permiso.");
            return true;
        }

        Player target = Bukkit.getPlayer(args[1]);
        if (target == null) {
            sender.sendMessage("§c§l✖ §7Jugador no encontrado.");
            return true;
        }

        int amount;
        try {
            amount = Integer.parseInt(args[2]);
            if (amount <= 0) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            sender.sendMessage("§c§l✖ §7Cantidad inválida. Debe ser un número positivo.");
            return true;
        }

        switch (action) {
            case "give" -> {
                coinManager.addCoins(target, amount);
                coinManager.saveData();
                sender.sendMessage(Component.empty()
                        .append(Component.text("§a§l✓ §7Se le dieron "))
                        .append(Component.text(amount + " monedas", GOLD))
                        .append(Component.text(" a ", GRAY))
                        .append(Component.text(target.getName(), ORANGE))
                        .append(Component.text(".", GRAY)));
                target.sendMessage(Component.empty()
                        .append(Component.text(" 🪙 ", GOLD))
                        .append(Component.text("¡Recibiste ", GRAY))
                        .append(Component.text(amount + " monedas", GOLD).decoration(TextDecoration.BOLD, true))
                        .append(Component.text("!", GRAY)));
                target.playSound(target.getLocation(), org.bukkit.Sound.ENTITY_EXPERIENCE_ORB_PICKUP, 0.8f, 1.2f);
            }
            case "remove" -> {
                if (!coinManager.removeCoins(target, amount)) {
                    sender.sendMessage("§c§l✖ §7El jugador no tiene suficientes monedas.");
                    return true;
                }
                coinManager.saveData();
                sender.sendMessage(Component.empty()
                        .append(Component.text("§a§l✓ §7Se le quitaron "))
                        .append(Component.text(amount + " monedas", RED))
                        .append(Component.text(" a ", GRAY))
                        .append(Component.text(target.getName(), ORANGE))
                        .append(Component.text(".", GRAY)));
            }
            case "set" -> {
                coinManager.setCoins(target, amount);
                coinManager.saveData();
                sender.sendMessage(Component.empty()
                        .append(Component.text("§a§l✓ §7Monedas de "))
                        .append(Component.text(target.getName(), ORANGE))
                        .append(Component.text(" establecidas a ", GRAY))
                        .append(Component.text(String.valueOf(amount), GOLD))
                        .append(Component.text(".", GRAY)));
            }
            default -> sendUsage(sender);
        }

        return true;
    }

    private void sendUsage(CommandSender sender) {
        sender.sendMessage("§6§l🪙 Comandos de Monedas:");
        sender.sendMessage("§e/coins balance §7- Ver tus monedas");
        sender.sendMessage("§e/coins check <jugador> §7- Ver monedas de otro");
        sender.sendMessage("§e/coins give <jugador> <cantidad> §7- Dar monedas");
        sender.sendMessage("§e/coins remove <jugador> <cantidad> §7- Quitar monedas");
        sender.sendMessage("§e/coins set <jugador> <cantidad> §7- Establecer monedas");
    }
}
