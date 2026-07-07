package com.servermc.prisongens.robot;

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
 * Fábrica de ítems Robot. Toda la información viaja con el ítem
 * mediante PersistentDataContainer: id, categoría, nivel y nombre custom.
 */
public class RobotItemFactory {

    private final PrisonGens plugin;
    private final NamespacedKey keyId, keyCat, keyLevel, keyName;

    public RobotItemFactory(PrisonGens plugin) {
        this.plugin = plugin;
        keyId = new NamespacedKey(plugin, "robot_id");
        keyCat = new NamespacedKey(plugin, "robot_cat");
        keyLevel = new NamespacedKey(plugin, "robot_level");
        keyName = new NamespacedKey(plugin, "robot_name");
    }

    // ═══ Creación ═══

    public ItemStack create(RobotCategory cat, int level) {
        return create(cat, level, null);
    }

    public ItemStack create(RobotCategory cat, int level, String customName) {
        ItemStack item = new ItemStack(cat.icon);
        ItemMeta meta = item.getItemMeta();
        PersistentDataContainer pdc = meta.getPersistentDataContainer();
        pdc.set(keyId, PersistentDataType.STRING, UUID.randomUUID().toString());
        pdc.set(keyCat, PersistentDataType.STRING, cat.name());
        pdc.set(keyLevel, PersistentDataType.INTEGER, Math.max(1, level));
        if (customName != null) pdc.set(keyName, PersistentDataType.STRING, customName);
        item.setItemMeta(meta);
        updateDisplay(item);
        return item;
    }

    /** Reconstruye nombre y lore a partir del PDC actual. */
    public void updateDisplay(ItemStack item) {
        if (!isRobot(item)) return;
        ItemMeta meta = item.getItemMeta();
        RobotCategory cat = getCategory(item);
        int level = getLevel(item);
        String customName = meta.getPersistentDataContainer().get(keyName, PersistentDataType.STRING);
        double mult = plugin.getRobotsConfig().getDouble("income-multiplier", 1.0);

        String name = customName != null
                ? cat.color + "§l⚙ " + customName + " §7[Nv." + level + "]"
                : cat.color + "§l⚙ " + cat.display + " §7[Nv." + level + "]";
        meta.setDisplayName(name);

        List<String> lore = new ArrayList<>();
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("§7Tier: " + cat.color + "★".repeat(Math.max(1, cat.tier)));
        lore.add("§7Nivel: §f" + level + "§7/§f" + cat.maxLevel);
        lore.add("§7Ingresos: §a$" + String.format("%.1f", cat.moneyPerSec * level * mult) + "§7/s");
        lore.add("§7Prob. Tokens: §6" + String.format("%.1f", Math.min(90, cat.tokenChance * 100 * level)) + "%§7/s");
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("");
        lore.add("§eShift+Click derecho §7ver estadísticas");
        lore.add("§eInsertar en el Administrador de Robots §7para activar");
        meta.setLore(lore);
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        item.setItemMeta(meta);
    }

    // ═══ Lectura ═══

    public boolean isRobot(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return false;
        return item.getItemMeta().getPersistentDataContainer().has(keyCat, PersistentDataType.STRING);
    }

    public String getId(ItemStack item) {
        if (!isRobot(item)) return null;
        return item.getItemMeta().getPersistentDataContainer().get(keyId, PersistentDataType.STRING);
    }

    public RobotCategory getCategory(ItemStack item) {
        if (!isRobot(item)) return null;
        return RobotCategory.fromString(item.getItemMeta().getPersistentDataContainer().get(keyCat, PersistentDataType.STRING));
    }

    public int getLevel(ItemStack item) {
        if (!isRobot(item)) return 1;
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(keyLevel, PersistentDataType.INTEGER, 1);
    }

    public String getCustomName(ItemStack item) {
        if (!isRobot(item)) return null;
        return item.getItemMeta().getPersistentDataContainer().get(keyName, PersistentDataType.STRING);
    }

    // ═══ Mutación ═══

    public void setLevel(ItemStack item, int level) {
        if (!isRobot(item)) return;
        ItemMeta meta = item.getItemMeta();
        meta.getPersistentDataContainer().set(keyLevel, PersistentDataType.INTEGER, Math.max(1, level));
        item.setItemMeta(meta);
        updateDisplay(item);
    }

    public void setCustomName(ItemStack item, String name) {
        if (!isRobot(item)) return;
        ItemMeta meta = item.getItemMeta();
        if (name == null) meta.getPersistentDataContainer().remove(keyName);
        else meta.getPersistentDataContainer().set(keyName, PersistentDataType.STRING, name);
        item.setItemMeta(meta);
        updateDisplay(item);
    }

    /** Costo de subir de nivel: base * nivel actual. */
    public long upgradeCost(ItemStack item) {
        RobotCategory cat = getCategory(item);
        if (cat == null) return Long.MAX_VALUE;
        return cat.upgradeBaseCost * Math.max(1, getLevel(item));
    }
}
