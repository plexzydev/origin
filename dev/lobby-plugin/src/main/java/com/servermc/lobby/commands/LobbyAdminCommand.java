package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * /lobbyadmin - Admin management commands.
 * 
 * Subcommands:
 *   /lobbyadmin reload - Reloads the plugin configuration
 */
public class LobbyAdminCommand implements CommandExecutor {

    private final LobbyCore plugin;

    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 85, 85);
    private static final TextColor CYAN = TextColor.color(85, 255, 255);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);

    public LobbyAdminCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("lobby.admin")) {
            sender.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("No tienes permisos.", RED)));
            return true;
        }

        if (args.length == 0 || !args[0].equalsIgnoreCase("reload")) {
            sender.sendMessage(Component.empty()
                    .append(Component.text(" ℹ ", CYAN))
                    .append(Component.text("Uso: /lobbyadmin reload", GRAY)));
            return true;
        }

        // Reload config
        plugin.reloadConfig();
        plugin.getScoreboardManager().reload();

        sender.sendMessage(Component.empty()
                .append(Component.text(" ✅ ", GREEN))
                .append(Component.text("Configuración recargada correctamente.", GREEN)));

        return true;
    }
}
