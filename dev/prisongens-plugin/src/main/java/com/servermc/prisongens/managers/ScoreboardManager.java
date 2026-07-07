package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import io.papermc.paper.scoreboard.numbers.NumberFormat;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
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

public class ScoreboardManager {

    private final PrisonGens plugin;
    private BukkitTask updateTask;
    private final Map<UUID, Scoreboard> playerBoards = new ConcurrentHashMap<>();

    private static final int MAX_LINES = 15;

    // Palette
    private static final TextColor TITLE_RED = TextColor.color(255, 60, 40);
    private static final TextColor ORANGE_BRIGHT = TextColor.color(255, 140, 0);
    private static final TextColor ORANGE = TextColor.color(255, 170, 0);
    private static final TextColor YELLOW = TextColor.color(255, 220, 50);
    private static final TextColor RED = TextColor.color(255, 70, 70);
    private static final TextColor DARK_RED = TextColor.color(200, 40, 40);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor GRAY = TextColor.color(150, 150, 150);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);

    public ScoreboardManager(PrisonGens plugin) {
        this.plugin = plugin;
    }

    public void startUpdateTask() {
        updateTask = Bukkit.getScheduler().runTaskTimerAsynchronously(plugin, () -> {
            for (Player player : Bukkit.getOnlinePlayers()) {
                Bukkit.getScheduler().runTask(plugin, () -> updateScoreboard(player));
            }
        }, 0L, 20L);
    }

    public void stopUpdateTask() {
        if (updateTask != null) updateTask.cancel();
    }

    public void createScoreboard(Player player) {
        Scoreboard board = Bukkit.getScoreboardManager().getNewScoreboard();

        Component title = Component.empty()
                .append(Component.text("  ", TITLE_RED))
                .append(Component.text("🔥 ", ORANGE))
                .append(Component.text("PRISIÓN GENS", TITLE_RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text(" 🔥", ORANGE));

        Objective obj = board.registerNewObjective("prisongens", Criteria.DUMMY, title);
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

        String rankName = "Recluso";
        EconomyManager eco = plugin.getEconomyManager();
        String money = eco.formatBalance(eco.getBalance(player, EconomyManager.MONEY));
        String tokens = eco.formatBalance(eco.getBalance(player, EconomyManager.TOKENS));
        String coins = eco.formatBalance(eco.getBalance(player, EconomyManager.COINS));
        String essences = eco.formatBalance(eco.getBalance(player, EconomyManager.ESSENCES));

        IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);
        String tag = island != null ? island.tag : "Ninguna";

        return new Component[] {
            Component.text("                           \u00A7r", DARK_RED).decoration(TextDecoration.STRIKETHROUGH, true),
            Component.empty().append(Component.text("🔥 ", ORANGE)).append(Component.text(date, YELLOW)).append(Component.text(" | ", DARK_GRAY)).append(Component.text(time, YELLOW)),
            Component.text(" "),
            Component.empty().append(Component.text("─ ", DARK_GRAY)).append(Component.text("PERFIL", ORANGE_BRIGHT).decoration(TextDecoration.BOLD, true)),
            Component.empty().append(Component.text(" 👑 ", ORANGE)).append(Component.text("Rango: ", GRAY)).append(Component.text(rankName, WHITE)),
            Component.empty().append(Component.text(" 🌴 ", GREEN)).append(Component.text("Isla: ", GRAY)).append(Component.text(tag, WHITE)),
            Component.text("  "),
            Component.empty().append(Component.text("─ ", DARK_GRAY)).append(Component.text("ECONOMÍA", ORANGE_BRIGHT).decoration(TextDecoration.BOLD, true)),
            Component.empty().append(Component.text(" 💰 ", GREEN)).append(Component.text("Dinero: ", GRAY)).append(Component.text("$" + money, GREEN)),
            Component.empty().append(Component.text(" 🔶 ", ORANGE)).append(Component.text("Tokens: ", GRAY)).append(Component.text(tokens, ORANGE)),
            Component.empty().append(Component.text(" 🪙 ", YELLOW)).append(Component.text("Monedas: ", GRAY)).append(Component.text(coins, YELLOW)),
            Component.empty().append(Component.text(" ✧ ", TextColor.color(255, 85, 255))).append(Component.text("Esencias: ", GRAY)).append(Component.text(essences, TextColor.color(255, 85, 255))),
            Component.text("   "),
            Component.empty().append(Component.text("\u00A7r     ")).append(Component.text("mc.origin.net", ORANGE).decoration(TextDecoration.BOLD, true)),
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
