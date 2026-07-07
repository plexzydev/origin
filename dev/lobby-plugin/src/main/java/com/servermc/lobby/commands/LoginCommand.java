package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.title.Title;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import java.time.Duration;

/**
 * /login <password> - Authenticates a registered player.
 */
public class LoginCommand implements CommandExecutor {

    private final LobbyCore plugin;

    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE = TextColor.color(255, 140, 0);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);

    public LoginCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Este comando solo puede ser ejecutado por un jugador.");
            return true;
        }

        if (plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ℹ ", ORANGE))
                    .append(Component.text("Ya tienes la sesión iniciada.", GRAY)));
            return true;
        }

        if (!plugin.getAuthManager().isRegistered(player.getUniqueId())) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("No estás registrado. Usa ", GRAY))
                    .append(Component.text("/register <contraseña> <contraseña>", WHITE).decoration(TextDecoration.BOLD, true)));
            return true;
        }

        if (args.length < 1) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("Uso: ", GRAY))
                    .append(Component.text("/login <contraseña>", WHITE)));
            return true;
        }

        boolean success = plugin.getAuthManager().login(player.getUniqueId(), args[0]);

        if (success) {
            // Success title on screen
            Title successTitle = Title.title(
                    Component.text("🔥 Origin Network", RED).decoration(TextDecoration.BOLD, true),
                    Component.text("¡Bienvenido, " + player.getName() + "!", YELLOW),
                    Title.Times.times(Duration.ofMillis(300), Duration.ofSeconds(3), Duration.ofMillis(500))
            );
            player.showTitle(successTitle);

            player.sendMessage(Component.empty()
                    .append(Component.text(" ✅ ", GREEN))
                    .append(Component.text("¡Sesión iniciada correctamente!", GREEN)));

            // Initialize player state
            plugin.getScoreboardManager().createScoreboard(player);
            plugin.getNpcManager().showNPCsToPlayer(player);
            plugin.getHotbarManager().giveItems(player);
            plugin.getCosmeticManager().restoreActiveCosmetics(player);
        } else {
            // Error title on screen
            Title errorTitle = Title.title(
                    Component.text("❌ Error", RED).decoration(TextDecoration.BOLD, true),
                    Component.text("Contraseña incorrecta", GRAY),
                    Title.Times.times(Duration.ofMillis(200), Duration.ofSeconds(2), Duration.ofMillis(300))
            );
            player.showTitle(errorTitle);

            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("Contraseña incorrecta.", RED)));
        }

        return true;
    }
}
