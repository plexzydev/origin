package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import io.papermc.paper.scoreboard.numbers.NumberFormat;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;
import org.bukkit.scoreboard.Criteria;
import org.bukkit.scoreboard.DisplaySlot;
import org.bukkit.scoreboard.Objective;
import org.bukkit.scoreboard.Scoreboard;
import org.bukkit.scoreboard.Team;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Scoreboard Manager - Origin Network Lobby
 * 
 * Lobby-specific design with red/orange/yellow palette:
 *
 *         ORIGIN
 *   ━━━━━━━━━━━━━━━━━━━
 *   🔥 dd/MM/yyyy | HH:mm
 *
 *   ─ PERFIL
 *   👑 Rango: Mortal
 *   🪙 Monedas: 0
 *
 *   ─ SERVIDOR
 *   👥 Online: X
 *   📶 Ping: Xms
 *
 *   origin.net
 *   ━━━━━━━━━━━━━━━━━━━
 */
public class ScoreboardManager {

    private final LobbyCore plugin;
    private BukkitTask updateTask;
    private final Map<UUID, Scoreboard> playerBoards = new ConcurrentHashMap<>();

    private static final int MAX_LINES = 13;

    // ═══ Configurable ═══
    private String serverTitle;
    private String serverIP;
    private String defaultRank;

    // ═══ Red / Orange / Yellow palette ═══
    private static final TextColor TITLE_RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE_BRIGHT = TextColor.color(255, 140, 0);
    private static final TextColor ORANGE = TextColor.color(255, 170, 0);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);
    private static final TextColor YELLOW_LIGHT = TextColor.color(255, 255, 100);
    private static final TextColor RED = TextColor.color(255, 70, 70);
    private static final TextColor DARK_RED = TextColor.color(200, 40, 40);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor GRAY = TextColor.color(150, 150, 150);
    private static final TextColor LIGHT_GRAY = TextColor.color(200, 200, 200);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor COIN_GOLD = TextColor.color(255, 200, 50);

    public ScoreboardManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadConfig();
    }

    private void loadConfig() {
        FileConfiguration config = plugin.getConfig();
        serverTitle = config.getString("scoreboard.title", "ORIGIN");
        serverIP = config.getString("scoreboard.server-ip", "mc.origin.net");
        defaultRank = config.getString("scoreboard.default-rank", "Mortal");
    }

    public void reload() {
        loadConfig();
    }

    public void startUpdateTask() {
        updateTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            for (Player player : Bukkit.getOnlinePlayers()) {
                if (plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
                    updateScoreboard(player);
                }
            }
        }, 0L, 20L);
    }

    public void stopUpdateTask() {
        if (updateTask != null) updateTask.cancel();
    }

    public void createScoreboard(Player player) {
        Scoreboard board = Bukkit.getScoreboardManager().getNewScoreboard();

        // Title: ORIGIN in bold red/orange gradient feel
        Component title = Component.empty()
                .append(Component.text("  ", TITLE_RED))
                .append(Component.text("🔥 ", ORANGE))
                .append(Component.text(serverTitle, TITLE_RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text(" 🔥", ORANGE));

        Objective obj = board.registerNewObjective("lobby", Criteria.DUMMY, title);
        obj.setDisplaySlot(DisplaySlot.SIDEBAR);
        obj.numberFormat(NumberFormat.blank());

        for (int i = 1; i <= MAX_LINES; i++) {
            String entry = getEntry(i);
            Team team = board.registerNewTeam("l" + i);
            team.addEntry(entry);
            team.prefix(Component.empty());
            obj.getScore(entry).setScore(i);
            obj.getScore(entry).numberFormat(NumberFormat.blank());
        }

        playerBoards.put(player.getUniqueId(), board);
        player.setScoreboard(board);
        updateScoreboard(player);
    }

    public void updateScoreboard(Player player) {
        if (!player.isOnline()) return;

        Scoreboard board = playerBoards.get(player.getUniqueId());
        if (board == null) {
            createScoreboard(player);
            return;
        }

        if (player.getScoreboard() != board) {
            player.setScoreboard(board);
        }

        Component[] lines = buildLines(player);

        for (int i = 0; i < MAX_LINES; i++) {
            Team team = board.getTeam("l" + (MAX_LINES - i));
            if (team != null && i < lines.length) {
                team.prefix(lines[i]);
            } else if (team != null) {
                team.prefix(Component.empty());
            }
        }
    }

    private Component[] buildLines(Player player) {
        LocalDateTime now = LocalDateTime.now();
        String date = now.format(DateTimeFormatter.ofPattern("dd/MM/yyyy"));
        String time = now.format(DateTimeFormatter.ofPattern("HH:mm"));

        int online = Bukkit.getOnlinePlayers().size();
        int maxPlayers = Bukkit.getMaxPlayers();
        int ping = player.getPing();
        TextColor pingColor = ping < 80 ? GREEN : ping < 150 ? YELLOW : RED;

        String rankName = defaultRank;
        int monedas = plugin.getCoinManager() != null ? plugin.getCoinManager().getCoins(player) : 0;

        return new Component[] {
            // Line 0: Top bar (wide to force scoreboard width)
            Component.text("                           \u00A7r", DARK_RED).decoration(TextDecoration.STRIKETHROUGH, true),

            // Line 1: 🔥 Date | Time
            Component.empty()
                .append(Component.text("🔥 ", ORANGE))
                .append(Component.text(date, YELLOW))
                .append(Component.text(" | ", DARK_GRAY))
                .append(Component.text(time, YELLOW)),

            // Line 2: spacer
            Component.text(" "),

            // Line 3: ─ PERFIL
            Component.empty()
                .append(Component.text("─ ", DARK_GRAY))
                .append(Component.text("PERFIL", ORANGE_BRIGHT).decoration(TextDecoration.BOLD, true)),

            // Line 4: 👑 Rango
            Component.empty()
                .append(Component.text(" 👑 ", ORANGE))
                .append(Component.text("Rango: ", GRAY))
                .append(Component.text(rankName, WHITE)),

            // Line 5: 🪙 Monedas (lobby currency)
            Component.empty()
                .append(Component.text(" 🪙 ", COIN_GOLD))
                .append(Component.text("Monedas: ", GRAY))
                .append(Component.text(String.valueOf(monedas), COIN_GOLD)),

            // Line 6: spacer
            Component.text("  "),

            // Line 7: ─ SERVIDOR
            Component.empty()
                .append(Component.text("─ ", DARK_GRAY))
                .append(Component.text("SERVIDOR", ORANGE_BRIGHT).decoration(TextDecoration.BOLD, true)),

            // Line 8: 👥 Online
            Component.empty()
                .append(Component.text(" 👥 ", YELLOW))
                .append(Component.text("Online: ", GRAY))
                .append(Component.text(online + "/" + maxPlayers, GREEN)),

            // Line 9: 📶 Ping
            Component.empty()
                .append(Component.text(" 📶 ", ORANGE))
                .append(Component.text("Ping: ", GRAY))
                .append(Component.text(ping + "ms", pingColor)),

            // Line 10: spacer
            Component.text("   "),

            // Line 11: Server IP (Centered like title)
            Component.empty()
                .append(Component.text("\u00A7r     "))
                .append(Component.text(serverIP, ORANGE).decoration(TextDecoration.BOLD, true)),

            // Line 12: Bottom bar (same width as top)
            Component.text("                           \u00A7r", DARK_RED).decoration(TextDecoration.STRIKETHROUGH, true),
        };
    }

    public void removeScoreboard(Player player) {
        playerBoards.remove(player.getUniqueId());
        player.setScoreboard(Bukkit.getScoreboardManager().getMainScoreboard());
    }

    private String getEntry(int score) {
        StringBuilder sb = new StringBuilder();
        String hex = String.format("%02x", score);
        for (char c : hex.toCharArray()) {
            sb.append("\u00A7").append(c);
        }
        sb.append("\u00A7r");
        return sb.toString();
    }
}
