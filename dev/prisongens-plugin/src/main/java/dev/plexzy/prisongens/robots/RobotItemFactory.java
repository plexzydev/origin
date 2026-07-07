package dev.plexzy.prisongens.robots;

import dev.plexzy.prisongens.utils.NBTUtil;
import org.bukkit.ChatColor;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataContainer;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.*;

public class RobotItemFactory {

    private final JavaPlugin plugin;

    // PDC Keys
    public static final String KEY_ROBOT_ID       = "robot_id";
    public static final String KEY_ROBOT_TYPE     = "robot_type";
    public static final String KEY_ROBOT_LEVEL    = "robot_level";
    public static final String KEY_ROBOT_XP       = "robot_xp";
    public static final String KEY_ROBOT_SPEED    = "robot_speed";
    public static final String KEY_ROBOT_RADIUS   = "robot_radius";
    public static final String KEY_ROBOT_STORAGE  = "robot_storage";
    public static final String KEY_ROBOT_EFF      = "robot_efficiency";
    public static final String KEY_ROBOT_TOKENS   = "robot_tokens_pa";
    public static final String KEY_ROBOT_MONEY    = "robot_money_pa";
    public static final String KEY_ROBOT_ACTIVE   = "robot_active";
    public static final String KEY_IS_ROBOT       = "is_robot";

    public RobotItemFactory(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Crea un nuevo ítem de robot de la categoría dada en nivel 1.
     */
    public ItemStack createRobot(RobotCategory category) {
        return createRobot(category, 1, 0L);
    }

    /**
     * Crea un nuevo ítem de robot con nivel y XP específicos.
     */
    public ItemStack createRobot(RobotCategory category, int level, long xp) {
        ItemStack item = new ItemStack(Material.PAPER);
        ItemMeta meta = item.getItemMeta();

        String id = UUID.randomUUID().toString();

        // Nombre
        meta.setDisplayName(category.getColor() + "⚙ Robot " + category.getDisplayName()
                + ChatColor.DARK_GRAY + " [Nv." + level + "]");

        // CustomModelData para textura
        meta.setCustomModelData(100 + category.getCustomModelData());

        // Lore
        meta.setLore(buildLore(category, level, xp, 1.0, category.getBaseSpeed(),
                category.getBaseRadius(), category.getBaseStorage(),
                category.getBaseTokensPerAction(), category.getBaseMoneyPerAction()));

        // PDC
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        pdc.set(key(KEY_IS_ROBOT),      PersistentDataType.BYTE,   (byte) 1);
        pdc.set(key(KEY_ROBOT_ID),      PersistentDataType.STRING, id);
        pdc.set(key(KEY_ROBOT_TYPE),    PersistentDataType.STRING, category.name());
        pdc.set(key(KEY_ROBOT_LEVEL),   PersistentDataType.INTEGER, level);
        pdc.set(key(KEY_ROBOT_XP),      PersistentDataType.LONG,    xp);
        pdc.set(key(KEY_ROBOT_SPEED),   PersistentDataType.DOUBLE,  category.getBaseSpeed());
        pdc.set(key(KEY_ROBOT_RADIUS),  PersistentDataType.INTEGER, category.getBaseRadius());
        pdc.set(key(KEY_ROBOT_STORAGE), PersistentDataType.INTEGER, category.getBaseStorage());
        pdc.set(key(KEY_ROBOT_EFF),     PersistentDataType.DOUBLE,  category.getBaseEfficiency());
        pdc.set(key(KEY_ROBOT_TOKENS),  PersistentDataType.LONG,    category.getBaseTokensPerAction());
        pdc.set(key(KEY_ROBOT_MONEY),   PersistentDataType.DOUBLE,  category.getBaseMoneyPerAction());
        pdc.set(key(KEY_ROBOT_ACTIVE),  PersistentDataType.BYTE,    (byte) 0);

        item.setItemMeta(meta);
        return item;
    }

    /**
     * Reconstruye el lore de un robot a partir de sus PDC datos actuales.
     */
    public ItemStack refreshLore(ItemStack item) {
        if (!isRobot(item)) return item;
        ItemMeta meta = item.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();

        RobotCategory cat   = RobotCategory.valueOf(pdc.get(key(KEY_ROBOT_TYPE), PersistentDataType.STRING));
        int level           = pdc.get(key(KEY_ROBOT_LEVEL),   PersistentDataType.INTEGER);
        long xp             = pdc.get(key(KEY_ROBOT_XP),      PersistentDataType.LONG);
        double eff          = pdc.get(key(KEY_ROBOT_EFF),     PersistentDataType.DOUBLE);
        double speed        = pdc.get(key(KEY_ROBOT_SPEED),   PersistentDataType.DOUBLE);
        int radius          = pdc.get(key(KEY_ROBOT_RADIUS),  PersistentDataType.INTEGER);
        int storage         = pdc.get(key(KEY_ROBOT_STORAGE), PersistentDataType.INTEGER);
        long tokens         = pdc.get(key(KEY_ROBOT_TOKENS),  PersistentDataType.LONG);
        double money        = pdc.get(key(KEY_ROBOT_MONEY),   PersistentDataType.DOUBLE);

        meta.setDisplayName(cat.getColor() + "⚙ Robot " + cat.getDisplayName()
                + ChatColor.DARK_GRAY + " [Nv." + level + "]");
        meta.setLore(buildLore(cat, level, xp, eff, speed, radius, storage, tokens, money));
        item.setItemMeta(meta);
        return item;
    }

    private List<String> buildLore(RobotCategory cat, int level, long xp,
                                   double eff, double speed, int radius,
                                   int storage, long tokens, double money) {
        long xpNeeded = cat.xpToLevel(level);
        String bar = buildBar(xp, xpNeeded, 20);

        return Arrays.asList(
                "",
                ChatColor.GRAY + "Categoría: " + cat.getColoredName(),
                ChatColor.GRAY + "Rareza: "    + getRarity(cat),
                "",
                ChatColor.YELLOW + "── Estadísticas ──",
                ChatColor.WHITE + " ⚡ Velocidad: "    + ChatColor.AQUA  + String.format("%.1f", speed) + "/s",
                ChatColor.WHITE + " 🔍 Radio: "        + ChatColor.AQUA  + radius + " bloques",
                ChatColor.WHITE + " 📦 Almacenamiento: " + ChatColor.AQUA + storage + " items",
                ChatColor.WHITE + " ⚙ Eficiencia: "   + ChatColor.AQUA  + String.format("%.1fx", eff),
                ChatColor.WHITE + " 💰 Dinero/tick: "  + ChatColor.GREEN + "$" + String.format("%.2f", money),
                ChatColor.WHITE + " 🪙 Tokens/tick: "  + ChatColor.GOLD  + tokens,
                "",
                ChatColor.YELLOW + "── Progreso ──",
                ChatColor.WHITE + " Nivel: "           + ChatColor.AQUA  + level,
                ChatColor.WHITE + " XP: "              + ChatColor.AQUA  + xp + "/" + xpNeeded,
                ChatColor.DARK_GRAY + " [" + bar + ChatColor.DARK_GRAY + "]",
                "",
                ChatColor.DARK_GRAY + "Shift + Click Derecho para ver opciones"
        );
    }

    private String buildBar(long current, long max, int width) {
        int filled = max == 0 ? width : (int) Math.min((double) current / max * width, width);
        return ChatColor.AQUA + "█".repeat(filled) + ChatColor.DARK_GRAY + "█".repeat(width - filled);
    }

    private String getRarity(RobotCategory cat) {
        return switch (cat) {
            case WOODEN    -> ChatColor.GRAY + "Común";
            case STONE     -> ChatColor.WHITE + "Poco Común";
            case IRON      -> ChatColor.AQUA + "Raro";
            case GOLD      -> ChatColor.YELLOW + "Épico";
            case DIAMOND   -> ChatColor.DARK_AQUA + "Legendario";
            case EMERALD   -> ChatColor.GREEN + "Mítico";
            case NETHERITE -> ChatColor.DARK_RED + "Ancestral";
            case LEGENDARY -> ChatColor.GOLD + "✦ DIVINO ✦";
        };
    }

    public boolean isRobot(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return false;
        PersistentDataContainer pdc = item.getItemMeta().getPersistentDataContainer();
        return pdc.has(key(KEY_IS_ROBOT), PersistentDataType.BYTE);
    }

    private NamespacedKey key(String k) {
        return new NamespacedKey(plugin, k);
    }
}
