package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCloseEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemFlag;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;

import java.util.Arrays;

/**
 * Base de todos los menús. Usa InventoryHolder para identificar
 * inventarios propios sin depender de títulos.
 */
public abstract class Menu implements InventoryHolder {

    protected final PrisonGens plugin;
    protected final Player viewer;
    protected Inventory inventory;

    public Menu(PrisonGens plugin, Player viewer, int size, String title) {
        this.plugin = plugin;
        this.viewer = viewer;
        this.inventory = Bukkit.createInventory(this, size, title);
    }

    @Override
    public Inventory getInventory() { return inventory; }

    public void open() {
        render();
        viewer.openInventory(inventory);
        viewer.playSound(viewer.getLocation(), Sound.BLOCK_CHEST_OPEN, 0.5f, 1.2f);
    }

    public void refresh() { render(); }

    /** Redibuja el contenido del inventario. */
    protected abstract void render();

    /** Maneja un click. El evento ya viene cancelado por defecto. */
    public abstract void onClick(InventoryClickEvent event);

    /** Menús que permiten mover ítems en ciertos slots pueden sobreescribir esto. */
    public boolean allowsInteraction(int rawSlot) { return false; }

    public void onClose(InventoryCloseEvent event) {}

    // ═══ Helpers ═══

    protected void fillBackground(Material mat) {
        ItemStack bg = item(mat, " ");
        for (int i = 0; i < inventory.getSize(); i++) inventory.setItem(i, bg);
    }

    protected ItemStack item(Material mat, String name, String... lore) {
        ItemStack it = new ItemStack(mat);
        ItemMeta meta = it.getItemMeta();
        meta.setDisplayName(name);
        if (lore.length > 0) meta.setLore(Arrays.asList(lore));
        meta.addItemFlags(ItemFlag.HIDE_ATTRIBUTES, ItemFlag.HIDE_ENCHANTS);
        it.setItemMeta(meta);
        return it;
    }

    protected void deny(String message) {
        viewer.sendMessage("§c§l✖ §7" + message);
        viewer.playSound(viewer.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
    }

    protected void success(String message) {
        viewer.sendMessage("§a§l✓ §7" + message);
        viewer.playSound(viewer.getLocation(), Sound.ENTITY_EXPERIENCE_ORB_PICKUP, 0.8f, 1.2f);
    }
}
