package com.servermc.lobby;

import com.servermc.lobby.commands.LoginCommand;
import com.servermc.lobby.commands.NPCCommand;
import com.servermc.lobby.commands.RegisterCommand;
import com.servermc.lobby.commands.SetSpawnCommand;
import com.servermc.lobby.commands.LobbyAdminCommand;
import com.servermc.lobby.commands.CosmeticsCommand;
import com.servermc.lobby.commands.CoinsCommand;
import com.servermc.lobby.cosmetics.CosmeticGUI;
import com.servermc.lobby.cosmetics.CosmeticManager;
import com.servermc.lobby.listeners.AuthListener;
import com.servermc.lobby.listeners.NPCListener;
import com.servermc.lobby.listeners.PlayerListener;
import com.servermc.lobby.managers.AuthManager;
import com.servermc.lobby.managers.NPCManager;
import com.servermc.lobby.managers.PremiumManager;
import com.servermc.lobby.managers.ScoreboardManager;
import com.servermc.lobby.managers.SpawnManager;
import com.servermc.lobby.managers.CoinManager;
import com.servermc.lobby.managers.HotbarManager;
import org.bukkit.Bukkit;
import org.bukkit.plugin.java.JavaPlugin;

public class LobbyCore extends JavaPlugin {

    private static LobbyCore instance;

    private ScoreboardManager scoreboardManager;
    private AuthManager authManager;
    private PremiumManager premiumManager;
    private SpawnManager spawnManager;
    private NPCManager npcManager;
    private com.servermc.lobby.managers.TabManager tabManager;
    private CosmeticManager cosmeticManager;
    private CosmeticGUI cosmeticGUI;
    private CoinManager coinManager;
    private HotbarManager hotbarManager;

    @Override
    public void onEnable() {
        instance = this;

        // Save default config
        saveDefaultConfig();

        // Initialize managers
        spawnManager = new SpawnManager(this);
        authManager = new AuthManager(this);
        premiumManager = new PremiumManager(this);
        scoreboardManager = new ScoreboardManager(this);
        npcManager = new NPCManager(this);
        tabManager = new com.servermc.lobby.managers.TabManager(this);
        coinManager = new CoinManager(this);
        hotbarManager = new HotbarManager(this);
        cosmeticManager = new CosmeticManager(this);
        cosmeticGUI = new CosmeticGUI(this);

        // Register commands
        getCommand("setspawn").setExecutor(new SetSpawnCommand(this));
        getCommand("login").setExecutor(new LoginCommand(this));
        getCommand("register").setExecutor(new RegisterCommand(this));
        getCommand("npc").setExecutor(new NPCCommand(this));
        getCommand("lobbyadmin").setExecutor(new LobbyAdminCommand(this));
        getCommand("cosmetics").setExecutor(new CosmeticsCommand(this));
        getCommand("coins").setExecutor(new CoinsCommand(this));

        // Register listeners
        Bukkit.getPluginManager().registerEvents(new PlayerListener(this), this);
        Bukkit.getPluginManager().registerEvents(new AuthListener(this), this);
        Bukkit.getPluginManager().registerEvents(new NPCListener(this), this);
        Bukkit.getPluginManager().registerEvents(cosmeticGUI, this);
        Bukkit.getPluginManager().registerEvents(hotbarManager, this);

        // Start tasks
        scoreboardManager.startUpdateTask();
        tabManager.startUpdateTask();
        cosmeticManager.startTickLoop();
        npcManager.spawnAllNPCs();

        // Register BungeeCord channel for proxy support
        getServer().getMessenger().registerOutgoingPluginChannel(this, "BungeeCord");

        // Reload support: create scoreboards for already online players
        for (org.bukkit.entity.Player p : org.bukkit.Bukkit.getOnlinePlayers()) {
            if (authManager.isAuthenticated(p.getUniqueId())) {
                scoreboardManager.createScoreboard(p);
                hotbarManager.giveItems(p);
            }
        }

        getLogger().info("§a[LobbyCore] Plugin habilitado correctamente!");
    }

    @Override
    public void onDisable() {
        if (scoreboardManager != null) scoreboardManager.stopUpdateTask();
        if (tabManager != null) tabManager.stopUpdateTask();
        if (cosmeticManager != null) {
            cosmeticManager.saveData();
            cosmeticManager.stopTickLoop();
        }
        if (npcManager != null) npcManager.despawnAllNPCs();
        if (authManager != null) authManager.saveData();
        if (premiumManager != null) premiumManager.saveData();
        if (coinManager != null) coinManager.saveData();

        getLogger().info("§c[LobbyCore] Plugin deshabilitado.");
    }

    public static LobbyCore getInstance() { return instance; }
    public ScoreboardManager getScoreboardManager() { return scoreboardManager; }
    public AuthManager getAuthManager() { return authManager; }
    public PremiumManager getPremiumManager() { return premiumManager; }
    public SpawnManager getSpawnManager() { return spawnManager; }
    public NPCManager getNpcManager() { return npcManager; }
    public com.servermc.lobby.managers.TabManager getTabManager() { return tabManager; }
    public CosmeticManager getCosmeticManager() { return cosmeticManager; }
    public CosmeticGUI getCosmeticGUI() { return cosmeticGUI; }
    public CoinManager getCoinManager() { return coinManager; }
    public HotbarManager getHotbarManager() { return hotbarManager; }
}
