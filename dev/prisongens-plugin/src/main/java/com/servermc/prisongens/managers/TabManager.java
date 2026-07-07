package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;

public class TabManager {

    private final PrisonGens plugin;
    private BukkitTask updateTask;

    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE = TextColor.color(255, 170, 0);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);

    public TabManager(PrisonGens plugin) {
        this.plugin = plugin;
    }

    public void startUpdateTask() {
        updateTask = Bukkit.getScheduler().runTaskTimerAsynchronously(plugin, () -> {
            for (Player player : Bukkit.getOnlinePlayers()) {
                updateTab(player);
            }
        }, 0L, 20L);
    }

    public void stopUpdateTask() {
        if (updateTask != null) updateTask.cancel();
    }

    public void updateTab(Player player) {
        Component header = Component.empty()
                .append(Component.text("\n"))
                .append(Component.text("🔥 ", ORANGE))
                .append(Component.text("ORIGIN NETWORK", RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text(" 🔥", ORANGE))
                .append(Component.text("\n\n"))
                .append(Component.text("Servidor: ", GRAY))
                .append(Component.text("Prisión Gens", ORANGE))
                .append(Component.text("\n"));

        Component footer = Component.empty()
                .append(Component.text("\n"))
                .append(Component.text("Ping: ", GRAY))
                .append(Component.text(player.getPing() + "ms", ORANGE))
                .append(Component.text(" | Jugadores: ", GRAY))
                .append(Component.text(Bukkit.getOnlinePlayers().size(), ORANGE))
                .append(Component.text("\n\n"))
                .append(Component.text("mc.origin.net", ORANGE).decoration(TextDecoration.BOLD, true))
                .append(Component.text("\n"));

        player.sendPlayerListHeaderAndFooter(header, footer);
    }
}
