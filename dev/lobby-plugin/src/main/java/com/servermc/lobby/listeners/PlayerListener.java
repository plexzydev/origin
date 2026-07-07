package com.servermc.lobby.listeners;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.managers.AuthManager;
import com.servermc.lobby.managers.PremiumManager;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.title.Title;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.time.Duration;

/**
 * Player Listener - Handles join/quit events.
 * Manages the authentication flow with on-screen titles.
 */
public class PlayerListener implements Listener {

    private final LobbyCore plugin;

    private static final TextColor ORANGE = TextColor.color(255, 140, 0);
    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);

    public PlayerListener(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        AuthManager auth = plugin.getAuthManager();
        PremiumManager premium = plugin.getPremiumManager();

        // Custom join message
        Component joinMsg = Component.empty()
                .append(Component.text("[", DARK_GRAY))
                .append(Component.text("+", GREEN).decoration(TextDecoration.BOLD, true))
                .append(Component.text("] ", DARK_GRAY))
                .append(Component.text(player.getName(), ORANGE))
                .append(Component.text(" se ha conectado", GRAY));
        event.joinMessage(joinMsg);

        // Start auth flow
        auth.startAuthFlow(player.getUniqueId());

        // Teleport to spawn immediately
        plugin.getSpawnManager().teleportToSpawn(player);

        // Handle auth flow after short delay
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (!player.isOnline()) return;

            // ═══ First time? Ask premium question ═══
            if (!premium.hasAnswered(player.getUniqueId())) {
                premium.askPremiumQuestion(player);
                showAuthTitle(player, "⚡ Bienvenido", "Responde la pregunta en el chat");
                return;
            }

            // ═══ Premium player? Auto-login ═══
            if (premium.isPremium(player.getUniqueId())) {
                auth.authenticatePremium(player.getUniqueId());
                plugin.getScoreboardManager().createScoreboard(player);
                plugin.getNpcManager().showNPCsToPlayer(player);
                plugin.getHotbarManager().giveItems(player);
                plugin.getCosmeticManager().restoreActiveCosmetics(player);

                Title welcomeTitle = Title.title(
                        Component.text("🔥 Origin Network", RED).decoration(TextDecoration.BOLD, true),
                        Component.text("¡Bienvenido, " + player.getName() + "!", YELLOW),
                        Title.Times.times(Duration.ofMillis(300), Duration.ofSeconds(3), Duration.ofMillis(500))
                );
                player.showTitle(welcomeTitle);
                return;
            }

            // ═══ Registered? Show login title ═══
            if (auth.isRegistered(player.getUniqueId())) {
                showAuthTitle(player, "🔒 Inicia Sesión", "/login <contraseña>");

                player.sendMessage(Component.empty());
                player.sendMessage(Component.empty()
                        .append(Component.text(" 🔒 ", ORANGE))
                        .append(Component.text("Usa ", GRAY))
                        .append(Component.text("/login <contraseña>", WHITE).decoration(TextDecoration.BOLD, true))
                        .append(Component.text(" para iniciar sesión.", GRAY)));
                player.sendMessage(Component.empty());

                // Keep showing the title periodically
                startAuthTitleReminder(player, "🔒 Inicia Sesión", "/login <contraseña>");
            } else {
                // ═══ Not registered? Show register title ═══
                showAuthTitle(player, "📝 Regístrate", "/register <contraseña> <contraseña>");

                player.sendMessage(Component.empty());
                player.sendMessage(Component.empty()
                        .append(Component.text(" 📝 ", ORANGE))
                        .append(Component.text("Usa ", GRAY))
                        .append(Component.text("/register <contraseña> <contraseña>", WHITE).decoration(TextDecoration.BOLD, true))
                        .append(Component.text(" para crear tu cuenta.", GRAY)));
                player.sendMessage(Component.empty());

                startAuthTitleReminder(player, "📝 Regístrate", "/register <contraseña> <contraseña>");
            }
        }, 15L);
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();

        // Custom quit message
        Component quitMsg = Component.empty()
                .append(Component.text("[", DARK_GRAY))
                .append(Component.text("-", RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text("] ", DARK_GRAY))
                .append(Component.text(player.getName(), ORANGE))
                .append(Component.text(" se ha desconectado", GRAY));
        event.quitMessage(quitMsg);

        // Cleanup
        plugin.getCosmeticManager().cleanupOnQuit(player);
        plugin.getScoreboardManager().removeScoreboard(player);
        plugin.getAuthManager().cleanup(player.getUniqueId());
        plugin.getPremiumManager().removePending(player.getUniqueId());
    }

    /**
     * Show a title on the player's screen for auth.
     */
    private void showAuthTitle(Player player, String titleText, String subtitleText) {
        Title.Times times = Title.Times.times(
                Duration.ofMillis(200),
                Duration.ofSeconds(5),
                Duration.ofMillis(500)
        );

        Title title = Title.title(
                Component.text(titleText, ORANGE).decoration(TextDecoration.BOLD, true),
                Component.text(subtitleText, WHITE),
                times
        );
        player.showTitle(title);
    }

    /**
     * Periodically remind unauthenticated players with on-screen title.
     */
    private void startAuthTitleReminder(Player player, String titleText, String subtitleText) {
        Bukkit.getScheduler().runTaskTimer(plugin, task -> {
            if (!player.isOnline() || plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
                task.cancel();
                return;
            }
            showAuthTitle(player, titleText, subtitleText);
        }, 100L, 100L); // Every 5 seconds
    }
}
