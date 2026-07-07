package com.servermc.lobby.managers;

import com.servermc.lobby.LobbyCore;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.player.PlayerDropItemEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerSwapHandItemsEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;

import java.util.ArrayList;
import java.util.List;

/**
 * HotbarManager - Gives fixed, immovable items in the hotbar.
 * Slot 4 (5th): Compass → Server Selector
 * Slot 8 (last): Blaze Rod → Cosmetics Menu
 */
public class HotbarManager implements Listener {

    private final LobbyCore plugin;

    private static final String SELECTOR_TITLE = "§c§l🔥 §6§lSelector de Modalidad §c§l🔥";

    // Item display name identifiers (used for click detection)
    private static final String COMPASS_NAME = "§6§l⚔ Selector de Modalidad";
    private static final String COSMETICS_NAME = "§d§l✦ Cosméticos";

    public HotbarManager(LobbyCore plugin) {
        this.plugin = plugin;
    }

    /**
     * Give the fixed hotbar items to a player.
     */
    public void giveItems(Player player) {
        player.getInventory().clear();

        // Slot 4 (5th slot): Compass - Server Selector
        ItemStack compass = createHotbarItem(Material.COMPASS, COMPASS_NAME,
                "§7Elige una modalidad para jugar.",
                "",
                "§eClick derecho para abrir →");
        player.getInventory().setItem(4, compass);

        // Slot 8 (last slot): Blaze Rod - Cosmetics
        ItemStack blazeRod = createHotbarItem(Material.BLAZE_ROD, COSMETICS_NAME,
                "§7Personaliza tu apariencia",
                "§7con partículas y mascotas.",
                "",
                "§eClick derecho para abrir →");
        player.getInventory().setItem(8, blazeRod);
    }

    /**
     * Open the server selector GUI.
     */
    public void openServerSelector(Player player) {
        Inventory inv = Bukkit.createInventory(null, 45, SELECTOR_TITLE);

        // Fill background with dark glass
        ItemStack bg = createGuiItem(Material.BLACK_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 45; i++) inv.setItem(i, bg);

        // Red glass border top row
        ItemStack border = createGuiItem(Material.RED_STAINED_GLASS_PANE, " ");
        for (int i = 0; i < 9; i++) inv.setItem(i, border);
        for (int i = 36; i < 45; i++) inv.setItem(i, border);
        inv.setItem(9, border); inv.setItem(17, border);
        inv.setItem(18, border); inv.setItem(26, border);
        inv.setItem(27, border); inv.setItem(35, border);

        // ═══ Game Modes ═══

        // PrisonGens (slot 20)
        ItemStack prisongens = createGuiItem(Material.DIAMOND_PICKAXE, "§a§lPrisión Gens",
                "",
                "§7Mina, genera recursos y",
                "§7 vende para ser el más rico.",
                "",
                "§7Estado: §aOnline",
                "§7Jugadores: §e0",
                "",
                "§eClick para jugar →");
        ItemMeta prisonMeta = prisongens.getItemMeta();
        prisonMeta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES);
        prisongens.setItemMeta(prisonMeta);
        inv.setItem(20, prisongens);

        // Coming soon slots
        ItemStack comingSoon1 = createGuiItem(Material.GRAY_STAINED_GLASS_PANE, "§7§l🔒 Próximamente",
                "",
                "§8Una nueva modalidad",
                "§8está en desarrollo...",
                "",
                "§7¡Mantente atento!");
        inv.setItem(22, comingSoon1);

        ItemStack comingSoon2 = createGuiItem(Material.GRAY_STAINED_GLASS_PANE, "§7§l🔒 Próximamente",
                "",
                "§8Una nueva modalidad",
                "§8está en desarrollo...",
                "",
                "§7¡Mantente atento!");
        inv.setItem(24, comingSoon2);

        player.openInventory(inv);
        player.playSound(player.getLocation(), Sound.BLOCK_CHEST_OPEN, 0.5f, 1.2f);
    }

    // ═══ Event Handlers ═══

    @EventHandler
    public void onPlayerInteract(PlayerInteractEvent event) {
        Player player = event.getPlayer();
        if (!plugin.getAuthManager().isAuthenticated(player.getUniqueId())) return;

        if (event.getAction() != Action.RIGHT_CLICK_AIR && event.getAction() != Action.RIGHT_CLICK_BLOCK) return;

        ItemStack item = event.getItem();
        if (item == null || !item.hasItemMeta() || !item.getItemMeta().hasDisplayName()) return;

        String name = item.getItemMeta().getDisplayName();

        if (name.equals(COMPASS_NAME)) {
            event.setCancelled(true);
            openServerSelector(player);
        } else if (name.equals(COSMETICS_NAME)) {
            event.setCancelled(true);
            plugin.getCosmeticGUI().openMainMenu(player);
        }
    }

    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;

        // ── Prevent ALL inventory interactions in the lobby (unless creative) ──
        if (player.getGameMode() != org.bukkit.GameMode.CREATIVE) {
            event.setCancelled(true);
        }

        String title = event.getView().getTitle();

        // ── Server Selector GUI ──
        if (!title.equals(SELECTOR_TITLE)) return;
        event.setCancelled(true);

        ItemStack clicked = event.getCurrentItem();
        if (clicked == null || clicked.getType() == Material.BLACK_STAINED_GLASS_PANE
                || clicked.getType() == Material.RED_STAINED_GLASS_PANE
                || clicked.getType() == Material.GRAY_STAINED_GLASS_PANE) return;

        if (event.getSlot() == 20) {
            // PrisonGens
            player.closeInventory();
            player.sendMessage(Component.text("§a§l✓ §7Conectando a Prisión Gens..."));
            player.playSound(player.getLocation(), Sound.ENTITY_ENDERMAN_TELEPORT, 0.8f, 1.2f);

            // Send to server via BungeeCord
            com.servermc.lobby.utils.ProxyUtils.sendToServer(plugin, player, "prisongens");
        }
    }

    @EventHandler
    public void onDrop(PlayerDropItemEvent event) {
        if (event.getPlayer().getGameMode() != org.bukkit.GameMode.CREATIVE) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onSwapHand(PlayerSwapHandItemsEvent event) {
        if (event.getPlayer().getGameMode() != org.bukkit.GameMode.CREATIVE) {
            event.setCancelled(true);
        }
    }

    private boolean isHotbarItem(ItemStack item) {
        if (item == null || !item.hasItemMeta() || !item.getItemMeta().hasDisplayName()) return false;
        String name = item.getItemMeta().getDisplayName();
        return name.equals(COMPASS_NAME) || name.equals(COSMETICS_NAME);
    }

    // ═══ Utility ═══
    private ItemStack createHotbarItem(Material material, String name, String... lore) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        List<String> loreList = new ArrayList<>();
        for (String line : lore) loreList.add(line);
        meta.setLore(loreList);
        item.setItemMeta(meta);
        return item;
    }

    private ItemStack createGuiItem(Material material, String name, String... lore) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) {
            List<String> loreList = new ArrayList<>();
            for (String line : lore) loreList.add(line);
            meta.setLore(loreList);
        }
        item.setItemMeta(meta);
        return item;
    }
}
