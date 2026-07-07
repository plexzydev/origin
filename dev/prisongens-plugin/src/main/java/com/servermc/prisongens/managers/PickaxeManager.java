package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.*;
import org.bukkit.enchantments.Enchantment;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;

import java.util.ArrayList;
import java.util.List;

public class PickaxeManager implements Listener {

    private final PrisonGens plugin;
    private static final String PICKAXE_ID = "§c§l⛏ §6§lPico de Prisión";
    private static final String MENU_TITLE = "§c§l⛏ §6§lMejoras del Pico";

    // Custom enchants stored in PersistentData
    public enum PrisonEnchant {
        EFFICIENCY("Eficiencia", "§e⚡", "Mina más rápido.", Material.GOLDEN_PICKAXE, 500, 50),
        FORTUNE("Fortuna", "§b💎", "Más drops por bloque.", Material.DIAMOND, 1000, 100),
        HASTE("Velocidad", "§6⏩", "Efecto Haste permanente.", Material.SUGAR, 750, 75),
        JACKHAMMER("Jackhammer", "§c🔨", "Mina toda la capa de un golpe.", Material.IRON_BLOCK, 5000, 500),
        EXPLOSIVE("Explosivo", "§4💥", "Explota un área 3x3 al minar.", Material.TNT, 3000, 300),
        LASER("Láser", "§d🔫", "Mina en línea recta 5 bloques.", Material.END_ROD, 4000, 400),
        TOKENGREED("Token Greed", "§6🔶", "Más tokens al minar.", Material.GOLD_INGOT, 2000, 200),
        AUTOSELL("Auto Sell", "§a💰", "Vende automáticamente al minar.", Material.EMERALD, 5000, 0);

        public final String name, symbol, desc;
        public final Material icon;
        public final int baseCost, costPerLevel;

        PrisonEnchant(String name, String symbol, String desc, Material icon, int baseCost, int costPerLevel) {
            this.name = name; this.symbol = symbol; this.desc = desc;
            this.icon = icon; this.baseCost = baseCost; this.costPerLevel = costPerLevel;
        }

        public int getCost(int currentLevel) {
            return baseCost + (costPerLevel * currentLevel);
        }

        public int getMaxLevel() {
            return this == AUTOSELL ? 1 : 100;
        }
    }

    public PickaxeManager(PrisonGens plugin) {
        this.plugin = plugin;
    }

    // ═══ Pickaxe Creation ═══

    public void givePickaxe(Player player) {
        player.getInventory().setItem(0, createPickaxe(new int[PrisonEnchant.values().length]));
    }

    public ItemStack createPickaxe(int[] levels) {
        ItemStack pick = new ItemStack(Material.DIAMOND_PICKAXE);
        ItemMeta meta = pick.getItemMeta();
        meta.setDisplayName(PICKAXE_ID);
        meta.setUnbreakable(true);
        meta.addItemFlags(ItemFlag.HIDE_UNBREAKABLE, ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);

        // Apply vanilla efficiency
        if (levels[0] > 0) meta.addEnchant(Enchantment.EFFICIENCY, Math.min(levels[0], 255), true);
        if (levels[1] > 0) meta.addEnchant(Enchantment.FORTUNE, Math.min(levels[1], 255), true);

        // Build lore
        List<String> lore = new ArrayList<>();
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        for (int i = 0; i < PrisonEnchant.values().length; i++) {
            PrisonEnchant pe = PrisonEnchant.values()[i];
            String lvl = levels[i] > 0 ? "§f" + levels[i] : "§8✖";
            lore.add("  " + pe.symbol + " §7" + pe.name + ": " + lvl);
        }
        lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
        lore.add("");
        lore.add("§eClick derecho §7para abrir mejoras");
        meta.setLore(lore);

        // Store levels in PersistentData
        for (int i = 0; i < PrisonEnchant.values().length; i++) {
            meta.getPersistentDataContainer().set(
                    new org.bukkit.NamespacedKey(plugin, "pe_" + PrisonEnchant.values()[i].name()),
                    PersistentDataType.INTEGER, levels[i]);
        }

        pick.setItemMeta(meta);
        return pick;
    }

    public boolean isPickaxe(ItemStack item) {
        if (item == null || item.getType() != Material.DIAMOND_PICKAXE) return false;
        if (!item.hasItemMeta() || !item.getItemMeta().hasDisplayName()) return false;
        return item.getItemMeta().getDisplayName().equals(PICKAXE_ID);
    }

    public int[] getStats(Player player) {
        ItemStack item = player.getInventory().getItem(0);
        return getStats(item);
    }

    public int[] getStats(ItemStack item) {
        int[] levels = new int[PrisonEnchant.values().length];
        if (item == null || !isPickaxe(item)) { levels[0] = 1; return levels; }
        for (int i = 0; i < PrisonEnchant.values().length; i++) {
            levels[i] = item.getItemMeta().getPersistentDataContainer().getOrDefault(
                    new org.bukkit.NamespacedKey(plugin, "pe_" + PrisonEnchant.values()[i].name()),
                    PersistentDataType.INTEGER, i == 0 ? 1 : 0);
        }
        return levels;
    }

    public int getLevel(Player player, PrisonEnchant enchant) {
        int[] stats = getStats(player);
        return stats[enchant.ordinal()];
    }

    // ═══ Right Click → Open Menu ═══

    @EventHandler
    public void onInteract(PlayerInteractEvent event) {
        if (event.getAction() != Action.RIGHT_CLICK_AIR && event.getAction() != Action.RIGHT_CLICK_BLOCK) return;
        if (!isPickaxe(event.getItem())) return;
        // Don't interfere with gen items
        if (plugin.getGensManager().isGenItem(event.getItem())) return;
        event.setCancelled(true);
        openUpgradeMenu(event.getPlayer());
    }

    // ═══ Upgrade Menu ═══

    public void openUpgradeMenu(Player player) {
        Inventory inv = Bukkit.createInventory(null, 45, MENU_TITLE);

        ItemStack bg = makeItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 45; i++) inv.setItem(i, bg);

        // Decorative borders
        ItemStack border = makeItem(Material.RED_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 9; i++) inv.setItem(i, border);
        for (int i = 36; i < 45; i++) inv.setItem(i, border);

        int[] stats = getStats(player);
        double tokens = plugin.getEconomyManager().getBalance(player, EconomyManager.TOKENS);

        // Place enchants in two rows
        int[] slots = {10, 11, 12, 13, 14, 15, 16, 22};
        PrisonEnchant[] enchants = PrisonEnchant.values();

        for (int i = 0; i < enchants.length && i < slots.length; i++) {
            PrisonEnchant pe = enchants[i];
            int level = stats[i];
            int cost = pe.getCost(level);
            boolean maxed = level >= pe.getMaxLevel();

            List<String> lore = new ArrayList<>();
            lore.add("§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬");
            lore.add("§7" + pe.desc);
            lore.add("");
            lore.add("§7Nivel: " + (level > 0 ? "§f" + level : "§cNo desbloqueado"));

            if (maxed) {
                lore.add("§a§l✓ MÁXIMO");
            } else {
                lore.add("§7Costo: §6" + cost + " tokens");
                lore.add(tokens >= cost ? "§a§l✓ Disponible" : "§c§l✖ Insuficiente");
                lore.add("");
                lore.add("§eClick para " + (level == 0 ? "desbloquear" : "mejorar"));
            }

            String dispName = pe.symbol + " §7" + pe.name + (level > 0 ? " §f[" + level + "]" : "");
            inv.setItem(slots[i], makeItem(pe.icon, dispName, lore.toArray(new String[0])));
        }

        // Pickaxe preview center
        inv.setItem(40, player.getInventory().getItem(0) != null ? player.getInventory().getItem(0).clone() : makeItem(Material.DIAMOND_PICKAXE, PICKAXE_ID));

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.BLOCK_ANVIL_USE, 0.5f, 1.2f);
    }

    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;
        if (!event.getView().getTitle().equals(MENU_TITLE)) return;
        event.setCancelled(true);

        int[] slots = {10, 11, 12, 13, 14, 15, 16, 22};
        PrisonEnchant[] enchants = PrisonEnchant.values();

        int slot = event.getSlot();
        for (int i = 0; i < enchants.length && i < slots.length; i++) {
            if (slot != slots[i]) continue;

            PrisonEnchant pe = enchants[i];
            int[] stats = getStats(player);
            int level = stats[i];

            if (level >= pe.getMaxLevel()) {
                player.sendMessage("§c§l✖ §7Este enchant ya está al máximo.");
                return;
            }

            int cost = pe.getCost(level);
            if (!plugin.getEconomyManager().removeBalance(player, EconomyManager.TOKENS, cost)) {
                player.sendMessage("§c§l✖ §7No tienes suficientes tokens (" + cost + ").");
                player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
                return;
            }

            stats[i]++;

            // Apply haste effect
            if (pe == PrisonEnchant.HASTE && stats[i] > 0) {
                player.addPotionEffect(new org.bukkit.potion.PotionEffect(
                        org.bukkit.potion.PotionEffectType.HASTE, Integer.MAX_VALUE, stats[i] - 1, true, false));
            }

            player.getInventory().setItem(0, createPickaxe(stats));
            plugin.getEconomyManager().saveData();
            player.sendMessage("§a§l✓ §7" + pe.name + " mejorado a nivel §f" + stats[i] + "§7!");
            player.playSound(player.getLocation(), Sound.BLOCK_ANVIL_USE, 0.8f, 1.5f);
            openUpgradeMenu(player); // Refresh
            return;
        }
    }

    private ItemStack makeItem(Material mat, String name, String... lore) {
        ItemStack item = new ItemStack(mat);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) {
            List<String> l = new ArrayList<>();
            for (String s : lore) l.add(s);
            meta.setLore(l);
        }
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        item.setItemMeta(meta);
        return item;
    }
}
