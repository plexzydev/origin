package com.servermc.prisongens.gen;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.NamespacedKey;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataContainer;
import org.bukkit.persistence.PersistentDataType;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Fábrica de ítems GEN. Toda la información del GEN viaja con el ítem
 * mediante PersistentDataContainer: id, categoría, nivel, xp, alimentados,
 * bonus de capacidad y nombre custom.
 */
public class GenItemFactory {

    private final PrisonGens plugin;
    private final NamespacedKey keyId, keyCat, keyLevel, keyXp, keyFed, keyCapBonus, keyName;

    public GenItemFactory(PrisonGens plugin) {
        this.plugin = plugin;
        keyId = new NamespacedKey(plugin, "gen_id");
        keyCat = new NamespacedKey(plugin, "gen_cat");
        keyLevel = new NamespacedKey(plugin, "gen_level");
        keyXp = new NamespacedKey(plugin, "gen_xp");
        keyFed = new NamespacedKey(plugin, "gen_fed");
        keyCapBonus = new NamespacedKey(plugin, "gen_cap_bonus");
        keyName = new NamespacedKey(plugin, "gen_name");
    }

    // ═══ Creación ═══

    public ItemStack create(GenCategory cat, int level) {
        return create(cat, level, 0, 0, 0, null);
    }

    public ItemStack create(GenCategory cat, int level, long xp, int fed, int capBonus, String customName) {
        ItemStack item = new ItemStack(cat.icon);
        ItemMeta meta = item.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        pdc.set(keyId, PersistentDataType.STRING, UUID.randomUUID().toString());
        pdc.set(keyCat, PersistentDataType.STRING, cat.name());
        pdc.set(keyLevel, PersistentDataType.INTEGER, Math.max(1, level));
        pdc.set(keyXp, PersistentDataType.LONG, Math.max(0, xp));
        pdc.set(keyFed, PersistentDataType.INTEGER, Math.max(0, fed));
        pdc.set(keyCapBonus, PersistentDataType.INTEGER, Math.max(0, capBonus));
        if (customName != null) pdc.set(keyName, PersistentDataType.STRING, customName);
        item.setItemMeta(meta);
        updateDisplay(item);
        return item;
    }

    /** Reconstruye nombre y lore a partir del PDC actual. */
    public void updateDisplay(ItemStack item) {
        if (!isGen(item)) return;
        ItemMeta meta = item.getItemMeta();
        GenCategory cat = getCategory(item);
        int level = getLevel(item);
        long xp = getXp(item);
        long next = xpForNextLevel(level);
        int fed = getFed(item);
        int cap = getCapacity(item);
        String customName = meta.getPersistentDataContainer().get(keyName, PersistentDataType.STRING);

        String name = customName != null
                ? cat.color + "§l⬢ " + customName + " §7[Nv." + level + "]"
                : cat.color + "§l⬢ " + cat.display + " §7[Nv." + level + "]";
        meta.setDisplayName(name);

        List<String> lore = new ArrayList<>();
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("§7Tier: " + cat.color + "★".repeat(Math.max(1, cat.tier)));
        lore.add("§7Nivel: §f" + level);
        lore.add("§7XP: §f" + xp + "§7/§f" + next + " " + progressBar(xp, next));
        lore.add("§7Alimentados: §f" + fed + "§7/§f" + cap);
        lore.add("§7Etapa máxima: §f" + cat.maxStage);
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("");
        lore.add("§eShift+Click derecho §7ver estadísticas");
        lore.add("§eInsertar en el Administrador de Minas §7para activar");
        meta.setLore(lore);
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        item.setItemMeta(meta);
    }

    private String progressBar(long xp, long next) {
        int filled = next <= 0 ? 10 : (int) Math.min(10, (xp * 10) / next);
        return "§8[" + "§a▮".repeat(filled) + "§7▮".repeat(10 - filled) + "§8]";
    }

    // ═══ Lectura ═══

    public boolean isGen(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return false;
        return item.getItemMeta().getPersistentDataContainer().has(keyCat, PersistentDataType.STRING);
    }

    public String getId(ItemStack item) {
        if (!isGen(item)) return null;
        return item.getItemMeta().getPersistentDataContainer().get(keyId, PersistentDataType.STRING);
    }

    public GenCategory getCategory(ItemStack item) {
        if (!isGen(item)) return null;
        return GenCategory.fromString(item.getItemMeta().getPersistentDataContainer().get(keyCat, PersistentDataType.STRING));
    }

    public int getLevel(ItemStack item) {
        if (!isGen(item)) return 1;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(keyLevel, PersistentDataType.INTEGER, 1);
    }

    public long getXp(ItemStack item) {
        if (!isGen(item)) return 0;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(keyXp, PersistentDataType.LONG, 0L);
    }

    public int getFed(ItemStack item) {
        if (!isGen(item)) return 0;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(keyFed, PersistentDataType.INTEGER, 0);
    }

    public int getCapBonus(ItemStack item) {
        if (!isGen(item)) return 0;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(keyCapBonus, PersistentDataType.INTEGER, 0);
    }

    /** Capacidad total: base por categoría + bonus comprado + bonus de mejora de isla se suma aparte. */
    public int getCapacity(ItemStack item) {
        GenCategory cat = getCategory(item);
        if (cat == null) return 0;
        return cat.baseFeedCapacity + getCapBonus(item);
    }

    public String getCustomName(ItemStack item) {
        if (!isGen(item)) return null;
        return item.getItemMeta().getPersistentDataContainer().get(keyName, PersistentDataType.STRING);
    }

    // ═══ Mutación ═══

    public void setCustomName(ItemStack item, String name) {
        if (!isGen(item)) return;
        ItemMeta meta = item.getItemMeta();
        if (name == null) meta.getPersistentDataContainer().remove(keyName);
        else meta.getPersistentDataContainer().set(keyName, PersistentDataType.STRING, name);
        item.setItemMeta(meta);
        updateDisplay(item);
    }

    public void addCapBonus(ItemStack item, int amount) {
        if (!isGen(item)) return;
        ItemMeta meta = item.getItemMeta();
        int current = meta.getPersistentDataContainer().getOrDefault(keyCapBonus, PersistentDataType.INTEGER, 0);
        meta.getPersistentDataContainer().set(keyCapBonus, PersistentDataType.INTEGER, current + amount);
        item.setItemMeta(meta);
        updateDisplay(item);
    }

    /**
     * Alimenta un GEN con otro GEN. Devuelve true si se pudo (capacidad disponible).
     * Actualiza XP, nivel y contador de alimentados en el PDC del ítem.
     */
    public boolean feed(ItemStack target, ItemStack food) {
        if (!isGen(target) || !isGen(food)) return false;
        int fed = getFed(target);
        if (fed >= getCapacity(target)) return false;

        GenCategory targetCat = getCategory(target);
        GenCategory foodCat = getCategory(food);
        if (targetCat == null || foodCat == null) return false;

        long gained = computeFeedXp(targetCat, foodCat, getLevel(food));
        ItemMeta meta = target.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        long xp = pdc.getOrDefault(keyXp, PersistentDataType.LONG, 0L) + gained;
        int level = pdc.getOrDefault(keyLevel, PersistentDataType.INTEGER, 1);

        // Subir niveles mientras alcance
        while (xp >= xpForNextLevel(level)) {
            xp -= xpForNextLevel(level);
            level++;
        }

        pdc.set(keyXp, PersistentDataType.LONG, xp);
        pdc.set(keyLevel, PersistentDataType.INTEGER, level);
        pdc.set(keyFed, PersistentDataType.INTEGER, fed + 1);
        target.setItemMeta(meta);
        updateDisplay(target);
        return true;
    }

    public long computeFeedXp(GenCategory target, GenCategory food, int foodLevel) {
        var cfg = plugin.getGensConfig();
        double equal = cfg.getDouble("feed-xp.equal-multiplier", 1.0);
        double lower = cfg.getDouble("feed-xp.lower-multiplier", 0.35);
        double higher = cfg.getDouble("feed-xp.higher-multiplier", 2.5);

        double mult;
        int diff = food.tier - target.tier;
        if (diff == 0) mult = equal;
        else if (diff < 0) mult = Math.pow(lower, -diff);
        else mult = Math.pow(higher, diff);

        return Math.max(1, (long) (food.feedBaseXp * mult * (1 + (foodLevel - 1) * 0.25)));
    }

    public long xpForNextLevel(int level) {
        long base = plugin.getGensConfig().getLong("base-xp-per-level", 100);
        return base * Math.max(1, level);
    }
}
