package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Authentication Manager - Handles player registration and login.
 * Stores credentials securely using SHA-256 hashing.
 * Players must authenticate before they can interact with the lobby.
 */
public class AuthManager {

    private final LobbyCore plugin;
    private File dataFile;
    private FileConfiguration dataConfig;

    // Authenticated players in this session
    private final Set<UUID> authenticated = ConcurrentHashMap.newKeySet();
    // Players currently in login/register flow
    private final Set<UUID> pendingAuth = ConcurrentHashMap.newKeySet();

    public AuthManager(LobbyCore plugin) {
        this.plugin = plugin;
        loadData();
    }

    private void loadData() {
        if (!plugin.getDataFolder().exists()) {
            plugin.getDataFolder().mkdirs();
        }
        dataFile = new File(plugin.getDataFolder(), "accounts.yml");
        if (!dataFile.exists()) {
            try { dataFile.createNewFile(); } catch (IOException e) { e.printStackTrace(); }
        }
        dataConfig = YamlConfiguration.loadConfiguration(dataFile);
    }

    /**
     * Check if a player is registered.
     */
    public boolean isRegistered(UUID uuid) {
        return dataConfig.contains("accounts." + uuid.toString());
    }

    /**
     * Check if a player is authenticated in this session.
     */
    public boolean isAuthenticated(UUID uuid) {
        return authenticated.contains(uuid);
    }

    /**
     * Check if a player needs to authenticate (not yet logged in).
     */
    public boolean needsAuth(UUID uuid) {
        return pendingAuth.contains(uuid);
    }

    /**
     * Mark player as needing authentication on join.
     */
    public void startAuthFlow(UUID uuid) {
        pendingAuth.add(uuid);
        authenticated.remove(uuid);
    }

    /**
     * Register a new account with password.
     * @return true if registration successful, false if already registered.
     */
    public boolean register(UUID uuid, String playerName, String password) {
        if (isRegistered(uuid)) return false;

        String hash = hashPassword(password);
        dataConfig.set("accounts." + uuid.toString() + ".name", playerName);
        dataConfig.set("accounts." + uuid.toString() + ".password", hash);
        saveData();

        authenticated.add(uuid);
        pendingAuth.remove(uuid);
        return true;
    }

    /**
     * Attempt to login with password.
     * @return true if login successful.
     */
    public boolean login(UUID uuid, String password) {
        if (!isRegistered(uuid)) return false;

        String stored = dataConfig.getString("accounts." + uuid.toString() + ".password", "");
        String hash = hashPassword(password);

        if (stored.equals(hash)) {
            authenticated.add(uuid);
            pendingAuth.remove(uuid);
            return true;
        }
        return false;
    }

    /**
     * Auto-authenticate premium players (skip login).
     */
    public void authenticatePremium(UUID uuid) {
        authenticated.add(uuid);
        pendingAuth.remove(uuid);
    }

    /**
     * Remove player auth state on disconnect.
     */
    public void cleanup(UUID uuid) {
        authenticated.remove(uuid);
        pendingAuth.remove(uuid);
    }

    public void saveData() {
        try {
            dataConfig.save(dataFile);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    /**
     * Hash password using SHA-256.
     */
    private String hashPassword(String password) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(password.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            e.printStackTrace();
            return password; // Fallback (should never happen)
        }
    }
}
