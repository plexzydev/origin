package dev.plexzy.prisongens.robots;

import dev.plexzy.prisongens.PrisonGens;
import org.bukkit.NamespacedKey;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.inventory.ItemStack;
import org.bukkit.persistence.PersistentDataContainer;
import org.bukkit.persistence.PersistentDataType;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public class RobotData {

    private String robotId;
    private RobotCategory category;
    private UUID ownerUuid;
    private UUID islandId;

    private int level;
    private long xp;
    private double speed;
    private int radius;
    private int storage;
    private double efficiency;
    private long tokensPerAction;
    private double moneyPerAction;

    // Offline buffers
    private double offlineMoney;
    private long offlineTokens;

    // Upgrade tiers por stat
    private final Map<RobotStat, Integer> upgradeTiers = new HashMap<>();

    // ── Constructor ───────────────────────────────────────────────────────────

    public RobotData(String robotId, RobotCategory category, int level, long xp,
                     double speed, int radius, int storage, double efficiency,
                     long tokensPerAction, double moneyPerAction) {
        this.robotId         = robotId;
        this.category        = category;
        this.level           = level;
        this.xp              = xp;
        this.speed           = speed;
        this.radius          = radius;
        this.storage         = storage;
        this.efficiency      = efficiency;
        this.tokensPerAction = tokensPerAction;
        this.moneyPerAction  = moneyPerAction;
        for (RobotStat s : RobotStat.values()) upgradeTiers.put(s, 0);
    }

    // ── Deserializar desde ItemStack ──────────────────────────────────────────

    public static RobotData fromItem(ItemStack item, PrisonGens plugin) {
        PersistentDataContainer pdc = item.getItemMeta().getPersistentDataContainer();
        String   id       = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_ID),      PersistentDataType.STRING);
        String   typeName = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_TYPE),    PersistentDataType.STRING);
        int      level    = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_LEVEL),   PersistentDataType.INTEGER);
        long     xp       = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_XP),      PersistentDataType.LONG);
        double   speed    = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_SPEED),   PersistentDataType.DOUBLE);
        int      radius   = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_RADIUS),  PersistentDataType.INTEGER);
        int      storage  = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_STORAGE), PersistentDataType.INTEGER);
        double   eff      = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_EFF),     PersistentDataType.DOUBLE);
        long     tokens   = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_TOKENS),  PersistentDataType.LONG);
        double   money    = pdc.get(nk(plugin, RobotItemFactory.KEY_ROBOT_MONEY),   PersistentDataType.DOUBLE);

        return new RobotData(id, RobotCategory.valueOf(typeName),
                level, xp, speed, radius, storage, eff, tokens, money);
    }

    // ── Serializar a ItemStack ────────────────────────────────────────────────

    public ItemStack toItem(PrisonGens plugin) {
        ItemStack item = plugin.getRobotManager().getFactory()
                .createRobot(category, level, xp);
        // Sobreescribir PDC con valores actuales
        ItemStack updated = updatePDC(item, plugin);
        return plugin.getRobotManager().getFactory().refreshLore(updated);
    }

    private ItemStack updatePDC(ItemStack item, PrisonGens plugin) {
        org.bukkit.inventory.meta.ItemMeta meta = item.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_LEVEL),   PersistentDataType.INTEGER, level);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_XP),      PersistentDataType.LONG,    xp);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_SPEED),   PersistentDataType.DOUBLE,  speed);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_RADIUS),  PersistentDataType.INTEGER, radius);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_STORAGE), PersistentDataType.INTEGER, storage);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_EFF),     PersistentDataType.DOUBLE,  efficiency);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_TOKENS),  PersistentDataType.LONG,    tokensPerAction);
        pdc.set(nk(plugin, RobotItemFactory.KEY_ROBOT_MONEY),   PersistentDataType.DOUBLE,  moneyPerAction);
        item.setItemMeta(meta);
        return item;
    }

    // ── Config ───────────────────────────────────────────────────────────────

    public void saveToConfig(org.bukkit.configuration.file.FileConfiguration cfg, String path) {
        cfg.set(path + ".id",        robotId);
        cfg.set(path + ".type",      category.name());
        cfg.set(path + ".owner",     ownerUuid != null ? ownerUuid.toString() : "");
        cfg.set(path + ".island",    islandId  != null ? islandId.toString()  : "");
        cfg.set(path + ".level",     level);
        cfg.set(path + ".xp",        xp);
        cfg.set(path + ".speed",     speed);
        cfg.set(path + ".radius",    radius);
        cfg.set(path + ".storage",   storage);
        cfg.set(path + ".eff",       efficiency);
        cfg.set(path + ".tokens",    tokensPerAction);
        cfg.set(path + ".money",     moneyPerAction);
        cfg.set(path + ".off_money", offlineMoney);
        cfg.set(path + ".off_tok",   offlineTokens);
        for (RobotStat s : RobotStat.values()) {
            cfg.set(path + ".tiers." + s.name(), upgradeTiers.getOrDefault(s, 0));
        }
    }

    public static RobotData fromConfig(ConfigurationSection s, PrisonGens plugin) {
        String   id      = s.getString("id");
        String   type    = s.getString("type");
        int      level   = s.getInt("level", 1);
        long     xp      = s.getLong("xp", 0L);
        double   speed   = s.getDouble("speed");
        int      radius  = s.getInt("radius");
        int      storage = s.getInt("storage");
        double   eff     = s.getDouble("eff");
        long     tokens  = s.getLong("tokens");
        double   money   = s.getDouble("money");

        RobotData rd = new RobotData(id, RobotCategory.valueOf(type),
                level, xp, speed, radius, storage, eff, tokens, money);

        String ownerStr  = s.getString("owner", "");
        String islandStr = s.getString("island", "");
        if (!ownerStr.isEmpty())  rd.setOwnerUuid(UUID.fromString(ownerStr));
        if (!islandStr.isEmpty()) rd.setIslandId(UUID.fromString(islandStr));

        rd.offlineMoney  = s.getDouble("off_money", 0);
        rd.offlineTokens = s.getLong("off_tok", 0);

        ConfigurationSection tiers = s.getConfigurationSection("tiers");
        if (tiers != null) {
            for (RobotStat st : RobotStat.values()) {
                rd.upgradeTiers.put(st, tiers.getInt(st.name(), 0));
            }
        }

        return rd;
    }

    // ── Getters / Setters ─────────────────────────────────────────────────────

    private static NamespacedKey nk(PrisonGens p, String k) {
        return new NamespacedKey(p, k);
    }

    public void addXp(long amount)            { this.xp += amount; }
    public void addOfflineMoney(double m)     { this.offlineMoney += m; }
    public void addOfflineTokens(long t)      { this.offlineTokens += t; }
    public int getUpgradeTier(RobotStat s)    { return upgradeTiers.getOrDefault(s, 0); }
    public void incrementUpgradeTier(RobotStat s) { upgradeTiers.merge(s, 1, Integer::sum); }

    public String getRobotId()         { return robotId; }
    public RobotCategory getCategory() { return category; }
    public UUID getOwnerUuid()         { return ownerUuid; }
    public UUID getIslandId()          { return islandId; }
    public int getLevel()              { return level; }
    public long getXp()                { return xp; }
    public double getSpeed()           { return speed; }
    public int getRadius()             { return radius; }
    public int getStorage()            { return storage; }
    public double getEfficiency()      { return efficiency; }
    public long getTokensPerAction()   { return tokensPerAction; }
    public double getMoneyPerAction()  { return moneyPerAction; }
    public double getOfflineMoney()    { return offlineMoney; }
    public long getOfflineTokens()     { return offlineTokens; }

    public void setOwnerUuid(UUID u)         { this.ownerUuid = u; }
    public void setIslandId(UUID i)          { this.islandId = i; }
    public void setLevel(int l)              { this.level = l; }
    public void setXp(long x)               { this.xp = x; }
    public void setSpeed(double s)           { this.speed = s; }
    public void setRadius(int r)             { this.radius = r; }
    public void setStorage(int s)            { this.storage = s; }
    public void setEfficiency(double e)      { this.efficiency = e; }
    public void setMoneyPerAction(double m)  { this.moneyPerAction = m; }
    public void setTokensPerAction(long t)   { this.tokensPerAction = t; }
    public void setOfflineMoney(double m)    { this.offlineMoney = m; }
    public void setOfflineTokens(long t)     { this.offlineTokens = t; }
}
