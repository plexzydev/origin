package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * /setspawn - Sets the lobby spawn point at the player's current location.
 */
public class SetSpawnCommand implements CommandExecutor {

    private final LobbyCore plugin;

    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 85, 85);
    private static final TextColor CYAN = TextColor.color(85, 255, 255);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);

    public SetSpawnCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Este comando solo puede ser ejecutado por un jugador.");
            return true;
        }

        if (!player.hasPermission("lobby.admin")) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("No tienes permisos.", RED)));
            return true;
        }

        plugin.getSpawnManager().setSpawn(player.getLocation());

        player.sendMessage(Component.empty()
                .append(Component.text(" ✅ ", GREEN))
                .append(Component.text("Spawn del lobby establecido en ", GRAY))
                .append(Component.text(String.format("%.1f, %.1f, %.1f",
                        player.getLocation().getX(),
                        player.getLocation().getY(),
                        player.getLocation().getZ()), CYAN)));

        return true;
    }
}
