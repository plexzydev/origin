package dev.plexzy.prisongens;

import dev.plexzy.prisongens.commands.PgAdminCommand;
import dev.plexzy.prisongens.enchants.EnchantManager;
import dev.plexzy.prisongens.enchants.listener.MineListener;
import dev.plexzy.prisongens.gen.GenManager;
import dev.plexzy.prisongens.gen.listener.GenItemListener;
import dev.plexzy.prisongens.island.IslandManager;
import dev.plexzy.prisongens.mine.MineManager;
import dev.plexzy.prisongens.npc.NpcManager;
import dev.plexzy.prisongens.robots.RobotManager;
import dev.plexzy.prisongens.upgrades.UpgradeManager;
import dev.plexzy.prisongens.utils.EconomyUtil;
import dev.plexzy.prisongens.utils.HologramUtil;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.Bukkit;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

public final class PrisonGens extends JavaPlugin {

    private static PrisonGens instance;

    // Managers
    private GenManager genManager;
    private MineManager mineManager;
    private RobotManager robotManager;
    private EnchantManager enchantManager;
    private UpgradeManager upgradeManager;
    private IslandManager islandManager;
    private NpcManager npcManager;
    private HologramUtil hologramUtil;

    // Economy
    private Economy economy;

    @Override
    public void onEnable() {
        instance = this;

        // Config por defecto
        saveDefaultConfig();

        // Vault
        if (!setupEconomy()) {
            getLogger().severe("[PrisonGens] No se encontró Vault. Desactivando...");
            Bukkit.getPluginManager().disablePlugin(this);
            return;
        }
        EconomyUtil.setEconomy(economy);

        // Inicializar managers en orden correcto
        this.hologramUtil    = new HologramUtil(this);
        this.islandManager   = new IslandManager(this);
        this.upgradeManager  = new UpgradeManager(this);
        this.mineManager     = new MineManager(this);
        this.genManager      = new GenManager(this);
        this.enchantManager  = new EnchantManager(this);
        this.robotManager    = new RobotManager(this);
        this.npcManager      = new NpcManager(this);

        // Registrar listeners
        Bukkit.getPluginManager().registerEvents(new GenItemListener(this), this);
        Bukkit.getPluginManager().registerEvents(new MineListener(this), this);

        // Registrar comandos
        PgAdminCommand adminCmd = new PgAdminCommand(this);
        getCommand("pgadmin").setExecutor(adminCmd);
        getCommand("pgadmin").setTabCompleter(adminCmd);
        getCommand("pg").setExecutor(new dev.plexzy.prisongens.commands.PgCommand(this));

        // Iniciar tareas periódicas
        startTasks();

        getLogger().info("[PrisonGens] ¡Plugin iniciado correctamente!");
    }

    @Override
    public void onDisable() {
        if (robotManager != null) robotManager.shutdown();
        if (mineManager  != null) mineManager.shutdown();
        if (genManager   != null) genManager.saveAll();
        if (upgradeManager != null) upgradeManager.saveAll();
        getLogger().info("[PrisonGens] Plugin desactivado. Datos guardados.");
    }

    private boolean setupEconomy() {
        if (getServer().getPluginManager().getPlugin("Vault") == null) return false;
        RegisteredServiceProvider<Economy> rsp =
                getServer().getServicesManager().getRegistration(Economy.class);
        if (rsp == null) return false;
        economy = rsp.getProvider();
        return economy != null;
    }

    private void startTasks() {
        // Robot worker tick cada 20 ticks (1 segundo)
        Bukkit.getScheduler().runTaskTimer(this,
                () -> robotManager.tickAllRobots(), 20L, 20L);

        // Auto-reset de minas: cada 5 segundos revisa si alguna mina necesita reinicio
        Bukkit.getScheduler().runTaskTimer(this,
                () -> mineManager.tickAutoResets(), 20L * 5, 20L * 5);

        // Guardar datos cada 5 minutos
        Bukkit.getScheduler().runTaskTimer(this, () -> {
            genManager.saveAll();
            upgradeManager.saveAll();
            robotManager.saveAll();
        }, 20L * 60 * 5, 20L * 60 * 5);
    }

    // ── Getters ──────────────────────────────────────────────────────────────

    public static PrisonGens getInstance() { return instance; }
    public GenManager getGenManager()           { return genManager; }
    public MineManager getMineManager()         { return mineManager; }
    public RobotManager getRobotManager()       { return robotManager; }
    public EnchantManager getEnchantManager()   { return enchantManager; }
    public UpgradeManager getUpgradeManager()   { return upgradeManager; }
    public IslandManager getIslandManager()     { return islandManager; }
    public NpcManager getNpcManager()           { return npcManager; }
    public HologramUtil getHologramUtil()       { return hologramUtil; }
    public Economy getEconomy()                 { return economy; }
}
