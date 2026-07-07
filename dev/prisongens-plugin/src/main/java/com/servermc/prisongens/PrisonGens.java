package com.servermc.prisongens;

import com.servermc.prisongens.commands.EconomyCommand;
import com.servermc.prisongens.commands.IslandCommand;
import com.servermc.prisongens.commands.SellCommand;
import com.servermc.prisongens.listeners.MineListener;
import com.servermc.prisongens.listeners.NPCClickListener;
import com.servermc.prisongens.listeners.PlayerListener;
import com.servermc.prisongens.managers.*;
import org.bukkit.Bukkit;
import org.bukkit.plugin.java.JavaPlugin;

public class PrisonGens extends JavaPlugin {

    private static PrisonGens instance;
    private EconomyManager economyManager;
    private IslandManager islandManager;
    private GensManager gensManager;
    private PickaxeManager pickaxeManager;
    private ScoreboardManager scoreboardManager;
    private TabManager tabManager;

    @Override
    public void onEnable() {
        instance = this;

        economyManager = new EconomyManager(this);
        islandManager = new IslandManager(this);
        gensManager = new GensManager(this);
        pickaxeManager = new PickaxeManager(this);
        scoreboardManager = new ScoreboardManager(this);
        tabManager = new TabManager(this);

        getCommand("is").setExecutor(new IslandCommand(this));
        getCommand("economy").setExecutor(new EconomyCommand(this));
        getCommand("sell").setExecutor(new SellCommand(this));

        Bukkit.getPluginManager().registerEvents(new PlayerListener(this), this);
        Bukkit.getPluginManager().registerEvents(new MineListener(this), this);
        Bukkit.getPluginManager().registerEvents(new NPCClickListener(this), this);
        Bukkit.getPluginManager().registerEvents(gensManager, this);
        Bukkit.getPluginManager().registerEvents(pickaxeManager, this);

        scoreboardManager.startUpdateTask();
        tabManager.startUpdateTask();
        gensManager.startRegenTask();

        getLogger().info("§a[PrisonGens] Plugin activado correctamente.");
    }

    @Override
    public void onDisable() {
        if (scoreboardManager != null) scoreboardManager.stopUpdateTask();
        if (tabManager != null) tabManager.stopUpdateTask();
        if (gensManager != null) { gensManager.stopRegenTask(); gensManager.saveData(); }
        if (economyManager != null) economyManager.saveData();
        if (islandManager != null) islandManager.saveData();
        getLogger().info("§c[PrisonGens] Plugin desactivado.");
    }

    public static PrisonGens getInstance() { return instance; }
    public EconomyManager getEconomyManager() { return economyManager; }
    public IslandManager getIslandManager() { return islandManager; }
    public GensManager getGensManager() { return gensManager; }
    public PickaxeManager getPickaxeManager() { return pickaxeManager; }
    public ScoreboardManager getScoreboardManager() { return scoreboardManager; }
    public TabManager getTabManager() { return tabManager; }
}
