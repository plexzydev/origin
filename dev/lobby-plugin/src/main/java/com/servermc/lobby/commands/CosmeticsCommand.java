package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.cosmetics.CosmeticGUI;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * /cosmetics - Opens the cosmetics menu.
 */
public class CosmeticsCommand implements CommandExecutor {

    private final LobbyCore plugin;

    public CosmeticsCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("§cEste comando solo puede ser usado por jugadores.");
            return true;
        }

        if (!plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
            player.sendMessage("§c§l✖ §7Debes iniciar sesión primero.");
            return true;
        }

        plugin.getCosmeticGUI().openMainMenu(player);
        return true;
    }
}
