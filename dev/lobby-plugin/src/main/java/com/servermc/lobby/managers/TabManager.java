package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;

/**
 * TabManager - Customizes the Tab List header and footer with matching aesthetic.
 */
public class TabManager {

    private final LobbyCore plugin;
    private BukkitTask updateTask;

    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE = TextColor.color(255, 140, 0);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);

    public TabManager(LobbyCore plugin) {
        this.plugin = plugin;
    }

    public void startUpdateTask() {
        updateTask = Bukkit.getScheduler().runTaskTimerAsynchronously(plugin, () -> {
            for (Player player : Bukkit.getOnlinePlayers()) {
                updateTabList(player);
            }
        }, 20L, 20L); // Update every second
    }

    public void stopUpdateTask() {
        if (updateTask != null && !updateTask.isCancelled()) {
            updateTask.cancel();
        }
    }

    private void updateTabList(Player player) {
        // Authenticated check
        if (!plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
            player.sendPlayerListHeaderAndFooter(
                Component.empty().append(Component.text("🔥 Origin Network 🔥", RED).decoration(TextDecoration.BOLD, true)),
                Component.empty().append(Component.text("Por favor, inicia sesión para jugar.", GRAY))
            );
            return;
        }

        int online = Bukkit.getOnlinePlayers().size();
        int max = Bukkit.getMaxPlayers();
        int ping = player.getPing();

        Component header = Component.empty()
                .append(Component.text("\n"))
                .append(Component.text("🔥 ", ORANGE))
                .append(Component.text("ORIGIN NETWORK", RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text(" 🔥", ORANGE))
                .append(Component.text("\n"))
                .append(Component.text("¡Bienvenido al Lobby Principal!", GRAY))
                .append(Component.text("\n"));

        Component footer = Component.empty()
                .append(Component.text("\n"))
                .append(Component.text(" 👥 Online: ", GRAY)).append(Component.text(online + "/" + max, YELLOW))
                .append(Component.text("  |  ", DARK_GRAY))
                .append(Component.text(" 📶 Ping: ", GRAY)).append(Component.text(ping + "ms", (ping < 100 ? TextColor.color(85, 255, 85) : RED)))
                .append(Component.text("\n\n"))
                .append(Component.text("Tienda: ", GRAY)).append(Component.text("tienda.origin.net", ORANGE))
                .append(Component.text("\n"));

        player.sendPlayerListHeaderAndFooter(header, footer);
    }
}
