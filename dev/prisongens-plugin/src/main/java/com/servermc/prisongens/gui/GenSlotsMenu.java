package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.mine.MineManager;
import org.bukkit.Material;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.ItemStack;

/**
 * Slots de GENS activos de la isla. Click con un GEN en el cursor
 * sobre un slot vacío → insertar. Click sobre un GEN activo → retirarlo.
 */
public class GenSlotsMenu extends Menu {

    private static final int[] SLOT_POSITIONS = {10, 11, 12, 13, 14, 15, 16, 19, 20, 21};

    public GenSlotsMenu(PrisonGens plugin, Player viewer) {
        super(plugin, viewer, 36, "§6§l⬢ GENS Activos");
    }

    @Override
    protected void render() {
        fillBackground(Material.BLACK_STAINED_GLASS_PANE);
        plugin.getMineManager().ensureSlots(viewer.getUniqueId());
        MineManager.MineData mine = plugin.getMineManager().getMine(viewer.getUniqueId());

        for (int i = 0; i < SLOT_POSITIONS.length; i++) {
            if (i < mine.genSlots.length) {
                ItemStack gen = mine.genSlots[i];
                if (gen != null) {
                    ItemStack display = gen.clone();
                    var meta = display.getItemMeta();
                    var lore = meta.hasLore() ? new java.util.ArrayList<>(meta.getLore()) : new java.util.ArrayList<String>();
                    lore.add("");
                    lore.add(i == 0 || isPrimary(mine, i) ? "§6§l★ GEN PRIMARIO" : "§7GEN secundario");
                    lore.add("§eClick para retirar");
                    meta.setLore(lore);
                    display.setItemMeta(meta);
                    inventory.setItem(SLOT_POSITIONS[i], display);
                } else {
                    inventory.setItem(SLOT_POSITIONS[i], item(Material.LIME_STAINED_GLASS_PANE,
                            "§a§l+ Slot Libre",
                            "", "§7Toma un GEN de tu inventario", "§7y haz click aquí para insertarlo."));
                }
            } else {
                inventory.setItem(SLOT_POSITIONS[i], item(Material.RED_STAINED_GLASS_PANE,
                        "§c§l✖ Slot Bloqueado",
                        "", "§7Desbloquea más slots con la", "§7mejora §fCapacidad de GENS§7."));
            }
        }

        inventory.setItem(31, item(Material.ARROW, "§7← Volver"));
    }

    private boolean isPrimary(MineManager.MineData mine, int index) {
        for (int i = 0; i < mine.genSlots.length; i++) {
            if (mine.genSlots[i] != null) return i == index;
        }
        return false;
    }

    @Override
    public void onClick(InventoryClickEvent event) {
        if (event.getSlot() == 31) { new MineAdminMenu(plugin, viewer).open(); return; }

        int slotIndex = -1;
        for (int i = 0; i < SLOT_POSITIONS.length; i++) {
            if (SLOT_POSITIONS[i] == event.getSlot()) { slotIndex = i; break; }
        }
        if (slotIndex == -1) return;

        MineManager.MineData mine = plugin.getMineManager().getMine(viewer.getUniqueId());
        if (slotIndex >= mine.genSlots.length) {
            deny("Este slot está bloqueado. Compra la mejora Capacidad de GENS.");
            return;
        }

        ItemStack current = mine.genSlots[slotIndex];
        ItemStack cursor = event.getCursor();

        if (current != null) {
            // Retirar GEN → vuelve con todo su estado
            if (viewer.getInventory().firstEmpty() == -1) {
                deny("Tu inventario está lleno.");
                return;
            }
            ItemStack out = plugin.getMineManager().withdrawGen(viewer.getUniqueId(), slotIndex);
            if (out != null) {
                viewer.getInventory().addItem(out);
                success("GEN retirado. Conserva todo su progreso.");
                viewer.playSound(viewer.getLocation(), Sound.ENTITY_ITEM_PICKUP, 0.8f, 0.9f);
            }
            refresh();
            return;
        }

        // Insertar: primero desde cursor, si no, buscar en la mano
        ItemStack toInsert = null;
        if (cursor != null && plugin.getGenItemFactory().isGen(cursor)) {
            toInsert = cursor;
        }
        if (toInsert == null) {
            // Buscar el primer GEN del inventario del jugador
            for (ItemStack it : viewer.getInventory().getContents()) {
                if (it != null && plugin.getGenItemFactory().isGen(it)) { toInsert = it; break; }
            }
        }
        if (toInsert == null) {
            deny("No tienes ningún GEN. Cómpralo en la tienda de GENS.");
            return;
        }

        ItemStack single = toInsert.clone();
        single.setAmount(1);
        mine.genSlots[slotIndex] = single;
        toInsert.setAmount(toInsert.getAmount() - 1);
        if (toInsert == cursor && toInsert.getAmount() <= 0) event.getView().setCursor(null);

        plugin.getMineManager().onGensChanged(viewer.getUniqueId());
        plugin.getMineManager().saveData();
        success("¡GEN insertado! Tu mina se está generando...");
        viewer.playSound(viewer.getLocation(), Sound.BLOCK_BEACON_ACTIVATE, 0.9f, 1.3f);
        refresh();
    }
}
