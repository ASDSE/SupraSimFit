import os
import tkinter as tk

from core.fitting.dba_dye_to_host import run_dba_dye_to_host_fitting
from gui.base_gui import BaseAppGUI

from core.progress_window import ProgressWindow


class DBAFittingAppDtoH(BaseAppGUI):
    def __init__(self, root):
        super().__init__(root, title="DBA Dye-to-Host Fitting Interface")
        self.file_path_var = self.add_string_var("file_path", "")
        self.use_dye_alone_results = self.add_bool_var("use_dye_alone_results", False)
        self.dye_alone_results_path = self.add_string_var("dye_alone_results_path", "")
        self.h0_var = self.add_double_var("h0", 6e-6)
        self.fit_trials_var = self.add_int_var("fit_trials", 200)
        self.rmse_threshold_var = self.add_double_var("rmse_threshold", 2)
        self.r2_threshold_var = self.add_double_var("r2_threshold", 0.9)
        self.enable_save_plots = self.add_bool_var("enable_save_plots", False)
        self.save_plots_dir = self.add_string_var("save_plots_dir", "")
        self.enable_display_plots = self.add_bool_var("enable_display_plots", True)
        self.enable_save_results = self.add_bool_var("enable_save_results", False)
        self.save_results_dir = self.add_string_var("save_results_dir", "")

        pad_x = self.pad_x
        pad_y = self.pad_y

        self.file_path_entry, self.file_path_browse = self.add_file_selector(
            row=0, label_text="Input File Path:", var=self.file_path_var
        )

        self.results_file_path_entry, self.results_file_button = (
            self.add_toggleable_file_selector(
                row=1,
                label_text="Read Boundaries from File: ",
                bool_var=self.use_dye_alone_results,
                file_var=self.dye_alone_results_path,
            )
        )

        self.h0_entry = self.add_labeled_entry(
            row=3, label_text="H₀ (M):", var=self.h0_var
        )
        self.fit_trials_entry = self.add_labeled_entry(
            row=4, label_text="Number of Fit Trials:", var=self.fit_trials_var
        )
        self.rmse_threshold_entry = self.add_labeled_entry(
            row=5, label_text="RMSE Threshold Factor:", var=self.rmse_threshold_var
        )
        self.r2_threshold_entry = self.add_labeled_entry(
            row=6, label_text="R² Threshold:", var=self.r2_threshold_var
        )

        self.results_dir_entry, self.results_dir_button = (
            self.add_toggleable_dir_selector(
                row=7,
                label_text="Save Plots To",
                bool_var=self.enable_save_plots,
                dir_var=self.save_plots_dir,
                input_file_var=self.file_path_var,
            )
        )
        self.results_save_dir_entry, self.results_save_dir_button = (
            self.add_toggleable_dir_selector(
                row=8,
                label_text="Save Results To",
                bool_var=self.enable_save_results,
                dir_var=self.save_results_dir,
                input_file_var=self.file_path_var,
            )
        )

        tk.Checkbutton(
            self.root, text="Display Plots", variable=self.enable_display_plots
        ).grid(row=9, column=0, columnspan=3, sticky=tk.W, padx=pad_x, pady=pad_y)
        tk.Button(self.root, text="Run Fitting", command=self.run_fitting).grid(
            row=10, column=0, columnspan=3, pady=10, padx=pad_x
        )
        
        self.add_tooltip(
            self.fit_trials_entry,
            "Number of random initializations for fitting. Higher values increase robustness but take longer.",
        )
        
        self.add_tooltip(
            self.rmse_threshold_entry,
            "Maximum allowed RMSE for a fit to be accepted. Lower values are stricter and may reject more fits; higher values are more permissive.",
        )
        
        self.add_tooltip(
            self.r2_threshold_entry,
            "Minimum R² for a fit to be accepted. Higher values are stricter and require better fits; lower values allow more fits.",
        )
        
        self.lift_and_focus()

    def run_fitting(self):
        try:
            file_path = self.file_path_entry.get()
            dye_alone_results = (
                self.dye_alone_results_path.get()
                if self.dye_alone_results_path.get()
                else None
            )
            h0_in_M = self.h0_var.get()
            rmse_threshold_factor = self.rmse_threshold_var.get()
            r2_threshold = self.r2_threshold_var.get()
            save_plots = self.enable_save_plots.get()
            display_plots = self.enable_display_plots.get()
            plots_dir = self.save_plots_dir.get()
            save_results = self.enable_save_results.get()
            results_save_dir = self.save_results_dir.get()
            number_of_fit_trials = self.fit_trials_var.get()

            # Show a progress indicator
            with ProgressWindow(
                self.root, "Fitting in Progress", "Fitting in progress, please wait..."
            ) as progress_window:
                result = run_dba_dye_to_host_fitting(
                    file_path=file_path,
                    results_file_path=dye_alone_results,
                    h0_in_M=h0_in_M,
                    rmse_threshold_factor=rmse_threshold_factor,
                    r2_threshold=r2_threshold,
                    save_plots=save_plots,
                    display_plots=display_plots,
                    plots_dir=plots_dir,
                    save_results_bool=save_results,
                    results_save_dir=results_save_dir,
                    number_of_fit_trials=number_of_fit_trials,
                    custom_x_label=None,
                    custom_plot_title=None,
                )
            if not result:
                self.show_message(
                    "No valid fits found. Try loosening thresholds, adjusting bounds, or double checking your raw data for outliers.",
                    is_error=True,
                )
            else:
                self.show_message("Fitting complete!", is_error=False)
        except Exception as e:
            self.show_message(f"Error: {str(e)}", is_error=True)


if __name__ == "__main__":
    root = tk.Tk()
    DBAFittingAppDtoH(root)
    root.mainloop()
