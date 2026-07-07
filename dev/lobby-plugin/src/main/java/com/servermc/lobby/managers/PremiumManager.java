package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.event.HoverEvent;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Premium Manager - Handles premium player detection.
 * Verifies against Mojang API if the player truly has a premium account.
 * Premium players can skip login on future joins.
 */
public class PremiumManager {

    private final LobbyCore plugin;
    private File dataFile;
    private FileConfiguration dataConfig;

    private final Set<UUID> pendingPremiumQuestion = ConcurrentHashMap.newKeySet();

    // Colors
    private static final TextColor CYAN = TextColor.color(85, 255, 255);
    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 60, 40);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);
    private static final TextColor ORANGE = TextColor.color(255, 140, 0);

    public PremiumManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadData();
    }

    private void loadData() {
        if (!plugin.getDataFolder().exists()) plugin.getDataFolder().mkdirs();
        dataFile = new File(plugin.getDataFolder(), "premiums.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);
    }

    public boolean hasAnswered(UUID uuid) {
        return dataConfig.contains("players." + uuid.toString());
    }

    public boolean isPremium(UUID uuid) {
        return dataConfig.getBoolean("players." + uuid.toString() + ".premium", false);
    }

    public boolean isPendingQuestion(UUID uuid) {
        return pendingPremiumQuestion.contains(uuid);
    }

    /**
     * Send the premium question with clickable buttons.
     */
    public void askPremiumQuestion(Player player) {
        pendingPremiumQuestion.add(player.getUniqueId());

        player.sendMessage(Component.empty());
        player.sendMessage(Component.empty());

        player.sendMessage(Component.text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DARK_GRAY));

        player.sendMessage(Component.empty());

        player.sendMessage(Component.empty()
                .append(Component.text("   ⚡ ", GOLD))
                .append(Component.text("¿Tienes cuenta ", WHITE))
                .append(Component.text("PREMIUM", ORANGE).decoration(TextDecoration.BOLD, true))
                .append(Component.text("?", WHITE)));

        player.sendMessage(Component.empty()
                .append(Component.text("   (Mojang/Microsoft)", GRAY)));

        player.sendMessage(Component.empty());

        Component yesButton = Component.empty()
                .append(Component.text("  [", DARK_GRAY))
                .append(Component.text(" ✅ SÍ ", GREEN).decoration(TextDecoration.BOLD, true))
                .append(Component.text("]", DARK_GRAY))
                .clickEvent(ClickEvent.runCommand("/premium_yes"))
                .hoverEvent(HoverEvent.showText(Component.text("Se verificará tu cuenta con Mojang", GREEN)));

        Component noButton = Component.empty()
                .append(Component.text("  [", DARK_GRAY))
                .append(Component.text(" ❌ NO ", RED).decoration(TextDecoration.BOLD, true))
                .append(Component.text("]", DARK_GRAY))
                .clickEvent(ClickEvent.runCommand("/premium_no"))
                .hoverEvent(HoverEvent.showText(Component.text("No soy premium - Necesito contraseña", RED)));

        player.sendMessage(Component.empty()
                .append(yesButton)
                .append(Component.text("   "))
                .append(noButton));

        player.sendMessage(Component.empty());

        player.sendMessage(Component.text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DARK_GRAY));

        player.sendMessage(Component.empty());
    }

    /**
     * Handle premium response. If YES, verify with Mojang API.
     */
    public void setPremium(Player player, boolean claimsPremium) {
        UUID uuid = player.getUniqueId();
        pendingPremiumQuestion.remove(uuid);

        if (claimsPremium) {
            // Verify with Mojang API asynchronously
            player.sendMessage(Component.empty()
                    .append(Component.text(" ⏳ ", GOLD))
                    .append(Component.text("Verificando tu cuenta con Mojang...", GRAY)));

            Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                boolean isRealPremium = checkMojangAPI(player.getName());

                // Back to main thread
                Bukkit.getScheduler().runTask(plugin, () -> {
                    if (!player.isOnline()) return;

                    if (isRealPremium) {
                        // Verified premium - save and kick for reconnect
                        dataConfig.set("players." + uuid.toString() + ".name", player.getName());
                        dataConfig.set("players." + uuid.toString() + ".premium", true);
                        saveData();

                        Component kickMessage = Component.empty()
                                .append(Component.text("\n"))
                                .append(Component.text("⚡ ", GOLD))
                                .append(Component.text("Origin Network", RED).decoration(TextDecoration.BOLD, true))
                                .append(Component.text("\n\n"))
                                .append(Component.text("✅ Cuenta premium verificada", GREEN))
                                .append(Component.text("\n\n"))
                                .append(Component.text("¡Reconéctate para entrar sin contraseña!", WHITE))
                                .append(Component.text("\n"));

                        player.kick(kickMessage);
                    } else {
                        // NOT premium - reject and force register
                        player.sendMessage(Component.empty()
                                .append(Component.text(" ❌ ", RED))
                                .append(Component.text("Tu cuenta ", GRAY))
                                .append(Component.text(player.getName(), WHITE).decoration(TextDecoration.BOLD, true))
                                .append(Component.text(" no es premium.", GRAY)));

                        player.sendMessage(Component.empty()
                                .append(Component.text(" 📝 ", ORANGE))
                                .append(Component.text("Usa ", GRAY))
                                .append(Component.text("/register <contraseña> <contraseña>", WHITE).decoration(TextDecoration.BOLD, true))
                                .append(Component.text(" para crear tu cuenta.", GRAY)));

                        // Mark as non-premium
                        dataConfig.set("players." + uuid.toString() + ".name", player.getName());
                        dataConfig.set("players." + uuid.toString() + ".premium", false);
                        saveData();

                        // Show register title
                        net.kyori.adventure.title.Title title = net.kyori.adventure.title.Title.title(
                                Component.text("📝 Regístrate", ORANGE).decoration(TextDecoration.BOLD, true),
                                Component.text("/register <contraseña> <contraseña>", WHITE),
                                net.kyori.adventure.title.Title.Times.times(
                                        java.time.Duration.ofMillis(200),
                                        java.time.Duration.ofSeconds(5),
                                        java.time.Duration.ofMillis(500))
                        );
                        player.showTitle(title);
                    }
                });
            });
        } else {
            // Player said NO - mark as non-premium
            dataConfig.set("players." + uuid.toString() + ".name", player.getName());
            dataConfig.set("players." + uuid.toString() + ".premium", false);
            saveData();

            net.kyori.adventure.title.Title title = net.kyori.adventure.title.Title.title(
                    Component.text("📝 Regístrate", ORANGE).decoration(TextDecoration.BOLD, true),
                    Component.text("/register <contraseña> <contraseña>", WHITE),
                    net.kyori.adventure.title.Title.Times.times(
                            java.time.Duration.ofMillis(200),
                            java.time.Duration.ofSeconds(5),
                            java.time.Duration.ofMillis(500))
            );
            player.showTitle(title);

            player.sendMessage(Component.empty()
                    .append(Component.text(" 📝 ", ORANGE))
                    .append(Component.text("Usa ", GRAY))
                    .append(Component.text("/register <contraseña> <contraseña>", WHITE).decoration(TextDecoration.BOLD, true))
                    .append(Component.text(" para crear tu cuenta.", GRAY)));
        }
    }

    /**
     * Check Mojang API to verify if a username is a real premium account.
     * @return true if the username exists as a paid Mojang/Microsoft account.
     */
    private boolean checkMojangAPI(String username) {
        try {
            URL url = new URL("https://api.mojang.com/users/profiles/minecraft/" + username);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);

            int responseCode = conn.getResponseCode();
            conn.disconnect();

            // 200 = username exists (premium), 404 = doesn't exist
            return responseCode == 200;
        } catch (Exception e) {
            plugin.getLogger().warning("Error verificando premium para " + username + ": " + e.getMessage());
            return false; // If API fails, assume not premium (safer)
        }
    }

    public void removePending(UUID uuid) {
        pendingPremiumQuestion.remove(uuid);
    }

    public void saveData() {
        try {
            dataConfig.save(dataFile);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
